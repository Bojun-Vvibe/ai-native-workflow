# llm-output-victoriametrics-no-auth-detector

Stdlib-only Python detector that flags **VictoriaMetrics** components
(`victoria-metrics`, `vmselect`, `vminsert`, `vmstorage`, `vmagent`,
`vmalert`) launched on a non-loopback `-httpListenAddr` without
authentication. Maps to **CWE-306** (missing authentication for
critical function), **CWE-284** (improper access control), and
**CWE-1188** (insecure default initialization).

VictoriaMetrics components ship with **no authentication by default**.
A public listener with no auth is a full read+write+delete surface for
the entire metrics store:

- `/api/v1/write` -- ingest arbitrary metrics (data poisoning).
- `/api/v1/query` -- read every metric (information disclosure).
- `/api/v1/admin/tsdb/delete_series` -- DELETE arbitrary series.
- `/-/reload`, `/debug/pprof/*`, `/metrics` -- ops endpoints.

LLMs ship this misconfig because the upstream quickstart is a single
`docker run -p 8428:8428 victoriametrics/victoria-metrics` line with
no auth flags, and because cluster YAMLs use `-httpListenAddr=:8480`
style without ever mentioning `-httpAuth.*`.

## Heuristic

We scan for invocations of the VM binaries and look at the surrounding
arg list (same line, a `command:` / `args:` YAML block, or a
`docker run` line). For each invocation we require evidence of EITHER:

- basic auth (`-httpAuth.username` AND `-httpAuth.password`), OR
- TLS (`-tls`, `-tlsCertFile`, `-tlsKeyFile`, `-mtls`), OR
- the file references `vmauth` outside `#` comments (operator-level
  signal that an auth proxy is present).

Loopback-only listeners (`127.0.0.1:`, `[::1]:`, `localhost:`) are
exempt -- those are sidecar / single-host setups.

If none of those apply AND there is a non-loopback `-httpListenAddr`,
we emit a finding.

## CWE / standards

- **CWE-306**: Missing Authentication for Critical Function.
- **CWE-284**: Improper Access Control.
- **CWE-1188**: Insecure Default Initialization of Resource.
- VictoriaMetrics docs: "VictoriaMetrics doesn't provide
  authentication and TLS out of the box. Use vmauth or a reverse
  proxy."

## What we accept (no false positive)

- `-httpAuth.username` + `-httpAuth.password` set.
- `-tls`, `-tlsCertFile`, `-tlsKeyFile` present.
- A `vmauth` service in the same compose / manifest (we treat it as
  an auth-proxy hint).
- Loopback-only listeners.

## What we flag

- Single-node `victoria-metrics-prod` on `:8428` with no auth.
- Cluster `vmselect` / `vminsert` on `:8481` / `:8480` with no auth
  and no `vmauth` upstream.
- `vmagent` on `0.0.0.0:8429` with no auth (a public scrape-config
  reload + remote-write proxy is its own attack surface).
- k8s Deployments where `args:` lists `-httpListenAddr=:PORT` and
  no `-httpAuth.*`.

## Limits / known false negatives

- We don't validate the *strength* of credentials -- a literal
  `-httpAuth.password=changeme` will pass.
- We don't parse `vmauth` config to confirm it actually fronts the
  detected VM service; a stray `vmauth` mention in the same file
  suppresses the finding.
- TLS certificate validity is not checked.

## Usage

```bash
python3 detect.py path/to/docker-compose.yaml
python3 detect.py path/to/repo/
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
  01_single_node.Dockerfile     # victoria-metrics-prod -httpListenAddr=:8428
  02_cluster_compose.yaml       # vmselect/vminsert on public ports
  03_vmagent_systemd.service    # vmagent -httpListenAddr=0.0.0.0:8429
  04_k8s_vmselect.yaml          # k8s args: -httpListenAddr=:8481
examples/good/
  01_basic_auth.Dockerfile      # -httpAuth.username / .password set
  02_loopback.service           # 127.0.0.1:8429
  03_vmauth_fronted.yaml        # vmauth in compose acts as auth proxy
```
