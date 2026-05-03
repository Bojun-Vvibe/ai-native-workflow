# llm-output-prometheus-pushgateway-no-auth-detector

Stdlib-only Python detector that flags **Prometheus Pushgateway**
deployments that expose the HTTP push endpoint (default port `9091`)
on a public bind address with **no authentication** -- no
`--web.config.file` pointing at a basic-auth / TLS-client-cert
config, no reverse-proxy hint.

Maps to **CWE-306** (missing authentication for critical function)
and **CWE-668** (exposure of resource to wrong sphere).

## Why this matters

Upstream `prom/pushgateway` (v1.x line, including v1.9.0) ships with
**no built-in authentication on `/metrics/job/...`**. The README is
explicit: "The Pushgateway does not perform any authentication."
Auth is delegated to either a reverse proxy or the
`--web.config.file` web TLS / basic-auth config described in
<https://prometheus.io/docs/prometheus/latest/configuration/https/>.

LLMs nevertheless emit:

```bash
docker run -p 9091:9091 prom/pushgateway
```

```yaml
args:
  - "--web.listen-address=0.0.0.0:9091"
```

```yaml
kind: Service
spec:
  type: LoadBalancer
  ports:
    - port: 9091
```

…and ship it to a network reachable from outside the trust boundary.
Anyone who can reach `:9091` can then `POST` arbitrary metric
series, poison alerting (mask real outages, fire fake ones), DoS
the gateway via unbounded label cardinality, and pollute long-term
storage.

Upstream reference (v1.x, current as of this template):

- <https://github.com/prometheus/pushgateway>
- README "Securing the Pushgateway" section.
- `--web.listen-address`, `--web.config.file` flags in
  `cmd/pushgateway/main.go`.

## Heuristic

A file is "pushgateway-related" if it mentions `prom/pushgateway`
or invokes the `pushgateway` binary with `--web.listen-address` /
`--web.config.file` / `--persistence.file`.

Inside such a file, outside `#` / `//` comments, we flag:

1. `--web.listen-address=0.0.0.0:<port>` or `=:<port>` (empty host)
   when **no** `--web.config.file=<non-empty>` appears in the same
   file.
2. Docker `-p [host:]9091:9091` where the host bind is not loopback
   and no `--web.config.file` is set.
3. docker-compose `ports:` entries publishing `9091:9091` next to a
   `prom/pushgateway` image with no `--web.config.file`.
4. k8s `Service` of `type: LoadBalancer` or `NodePort` with
   `port`/`targetPort` `9091` in a manifest that references
   `prom/pushgateway` and does not set `--web.config.file`.

Each occurrence emits one finding line.

## What we accept (no false positive)

- `-p 127.0.0.1:9091:9091` (loopback bind for local dev).
- A Deployment with `--web.listen-address=0.0.0.0:9091` AND a
  `--web.config.file=/etc/pushgateway/web.yml`.
- k8s `Service` of `type: ClusterIP` (assumed in-cluster traffic
  governed by NetworkPolicy / sidecar).
- README / runbook files that mention the bad form only as a
  warning in comments.

## What we flag

- Tutorial-style `docker run -p 9091:9091 prom/pushgateway`.
- k8s Deployment whose `args:` include
  `--web.listen-address=0.0.0.0:9091` without `--web.config.file`.
- `docker-compose.yml` publishing `9091:9091` next to a
  `prom/pushgateway` image with no `--web.config.file`.
- k8s `Service: LoadBalancer` exposing port `9091`.

## Limits / known false negatives

- We do not inspect NetworkPolicy / firewall rules that might
  re-restrict a `LoadBalancer`. A finding here means "you need to
  prove the wrapper is doing that work."
- We do not parse Helm values; if `--web.listen-address` and
  `--web.config.file` are templated and only resolved at install
  time, we may miss it.
- We do not inspect the contents of the file referenced by
  `--web.config.file`; an empty / no-auth config will still be
  treated as "authed" by this detector. Pair with a config-content
  linter for full coverage.

## Usage

```bash
python3 detect.py path/to/repo/
python3 detect.py docker-compose.yaml deploy/pushgateway.yaml
```

Exit codes: `0` = no findings, `1` = findings (printed to stdout),
`2` = usage error.

## Smoke test

```
$ bash smoke.sh
bad=4/4 good=0/3
PASS
```

Layout:

```
examples/bad/
  01_docker_run.sh        # docker run -p 9091:9091 prom/pushgateway
  02_listen_addr.yaml     # args: --web.listen-address=0.0.0.0:9091
  03_compose.yaml         # compose publishes 9091:9091
  04_service_lb.yaml      # k8s Service type: LoadBalancer port: 9091
examples/good/
  01_loopback_docker.sh   # -p 127.0.0.1:9091:9091
  02_with_web_config.yaml # listens public but uses --web.config.file
  03_doc_only.yaml        # only mentions bad form in comments
```
