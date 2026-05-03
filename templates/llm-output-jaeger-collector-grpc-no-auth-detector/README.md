# llm-output-jaeger-collector-grpc-no-auth-detector

Stdlib-only Python detector that flags **Jaeger collector** /
**all-in-one** deployments which expose the gRPC span-ingest ports
(OTLP `4317`, `jaeger.proto` `14250`) on a public bind address with
**no authentication**.

Maps to **CWE-306** (missing authentication for critical function)
and **CWE-668** (exposure of resource to wrong sphere).

## Why this matters

Upstream `jaegertracing/jaeger` (v1.x line, including v1.57) has, by
design, **no built-in authentication on the collector ingest
endpoints**. The docs say it must sit behind a private network or an
authenticating sidecar.

LLMs nevertheless love to emit:

```bash
docker run -p 4317:4317 -p 14250:14250 jaegertracing/all-in-one
```

```yaml
args:
  - "--collector.grpc-server.host-port=0.0.0.0:14250"
```

```yaml
kind: Service
spec:
  type: LoadBalancer
  ports:
    - port: 4317
```

…and ship it onto a network reachable from outside the trust
boundary. Anyone who reaches `4317` / `14250` can then inject
arbitrary spans, poison dashboards, exhaust storage, and push crafted
strings into the org's observability pipeline.

Upstream reference (v1.x, current as of this template):

- <https://github.com/jaegertracing/jaeger>
- `cmd/collector/app/options.go` (`--collector.grpc-server.host-port`,
  `--collector.otlp.grpc.host-port`)
- README "Security" section: collector has no built-in auth.

## Heuristic

We flag any of the following, outside `#` / `//` comments:

1. `--collector.grpc-server.host-port=0.0.0.0:<port>` or `:<port>`
   (empty host = bind all interfaces).
2. `--collector.otlp.grpc.host-port=0.0.0.0:<port>` or `:<port>`.
3. Docker `-p [host:]14250:14250` / `-p [host:]4317:4317` where the
   host bind is not loopback (`127.*` / `localhost` / `::1`).
4. docker-compose `ports:` entries that publish `14250` / `4317` in
   the same file as a `jaegertracing/all-in-one` or
   `jaegertracing/jaeger-collector` image, without a loopback bind.
5. k8s `Service` of `type: LoadBalancer` or `NodePort` with
   `port`/`targetPort` `14250` or `4317` in a manifest that
   references a `jaegertracing/` image.

Each occurrence emits one finding line.

## What we accept (no false positive)

- `-p 127.0.0.1:14250:14250` (loopback bind for local dev).
- `--collector.grpc-server.host-port=127.0.0.1:14250`.
- k8s `Service` of `type: ClusterIP` exposing `14250` / `4317`
  (assumed in-cluster traffic with NetworkPolicy elsewhere).
- README / runbook files that mention the bad form only as a
  warning.

## What we flag

- Tutorial-style `docker run -p 4317:4317 jaegertracing/all-in-one`.
- k8s Deployment whose `args:` include
  `--collector.grpc-server.host-port=0.0.0.0:14250`.
- `docker-compose.yml` publishing `14250:14250` next to a
  `jaegertracing/all-in-one` image.
- k8s `Service: LoadBalancer` exposing `4317` / `14250`.

## Limits / known false negatives

- We do not parse Helm values; if the dangerous bind is templated
  and only resolved at install time, we miss it.
- We do not inspect NetworkPolicy / firewall rules that might
  re-restrict a `LoadBalancer`. A finding here is "you need to be
  sure the wrapper is doing that work."

## Usage

```bash
python3 detect.py path/to/repo/
python3 detect.py docker-compose.yaml deploy/jaeger.yaml
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
  01_docker_run.sh           # docker run -p 4317:4317 ...
  02_collector_args.yaml     # args: --collector.grpc-server.host-port=0.0.0.0
  03_compose.yaml            # compose publishes 14250:14250 + 4317:4317
  04_service_lb.yaml         # k8s Service type: LoadBalancer port: 4317
examples/good/
  01_loopback_docker.sh      # -p 127.0.0.1:14250:14250
  02_clusterip_service.yaml  # ClusterIP + 127.0.0.1 host-port
  03_doc_only.yaml           # only mentions bad form in comments
```
