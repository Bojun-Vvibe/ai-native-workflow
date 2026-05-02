# llm-output-traefik-api-insecure-true-detector

Stdlib-only Python detector that flags **Traefik** (v2/v3) deployments
that enable the dashboard / API in **insecure mode**. Maps to
**CWE-306** (Missing Authentication for Critical Function),
**CWE-419** (Unprotected Primary Channel), **CWE-1188** (Insecure
Default Initialization), **CWE-200** (Information Exposure), OWASP
**A05:2021 Security Misconfiguration**.

The Traefik option `--api.insecure=true` (or `[api] insecure = true`
in TOML, `api: { insecure: true }` in YAML) tells Traefik to expose
the entire API and dashboard on the **`traefik` entrypoint**, the
**default port `:8080`**, with **no authentication, no TLS, no
middleware** in front of it.

The Traefik docs:

> "WARNING: Enabling the API in production is not recommended,
>  because it will expose all configuration elements, including
>  sensitive data."
>  -- https://doc.traefik.io/traefik/operations/api/

The API exposes:

- every router and its rule (paths, hosts, headers, regex),
- every service and its **backend URL** (often internal addresses
  that should never leak),
- the configured TLS certificates' subject and SANs,
- dynamic config providers (Docker socket paths, Consul/Etcd
  endpoints),
- health, metrics, and entrypoint topology.

Pair it with the Docker provider (the default tutorial pattern) and
the API also reveals every container label and every backend service
URL Traefik knows about. In a multi-tenant or internet-exposed
environment that is a full infrastructure map.

## Why LLMs ship this

Every "Traefik in 5 minutes" blog post turns on `--api.insecure=true`
because it is the only way to see the dashboard without setting up a
router + middleware + basic-auth. The model copies the demo straight
into a production docker-compose / k8s manifest.

## Heuristic

We flag any of:

1. **CLI flag** in shell, Dockerfile `CMD`/`ENTRYPOINT`,
   docker-compose `command:`, k8s `args:`, systemd `ExecStart=`:
   - `--api.insecure=true`
   - `--api.insecure true`
   - bare `--api.insecure` (Traefik treats it as `true`)

2. **TOML file provider** (`traefik.toml`, `*.toml`):
   ```toml
   [api]
     insecure = true
   ```

3. **YAML file provider** (`traefik.yaml`, helm values):
   ```yaml
   api:
     insecure: true
   ```

We do NOT flag:

- `[api] dashboard = true` on its own (dashboard with a router +
  auth middleware is the supported production pattern),
- `--api=true` (the API itself, fronted by a router, is fine),
- `--api.insecure=false` or `insecure: false`,
- README / comments mentioning the bad option.

## What we accept (no false positive)

- `api: { dashboard: true, insecure: false }` (production form).
- Dashboard exposed via labels:
  `traefik.http.routers.dash.rule=Host(...)` +
  `traefik.http.routers.dash.middlewares=auth` (compose example
  ships in `examples/good/`).
- Documentation files that quote the bad pattern only inside
  `#`-comments.

## What we flag

- docker-compose `command: ["--api.insecure=true", ...]`.
- k8s Deployment `args: ["--api.insecure=true", ...]`.
- Dockerfile `CMD ["traefik", "--api.insecure=true", ...]`.
- TOML `[api]` with `insecure = true`.
- YAML `api:` block with `insecure: true`.
- systemd `ExecStart=... --api.insecure=true ...`.

## Limits / known false negatives

- We do not flag environment-variable form
  `TRAEFIK_API_INSECURE=true` (Traefik supports it but it is rarely
  used; will be added in a follow-up if it appears in the wild).
- We do not parse Helm chart `_helpers.tpl` Sprig templating; helm
  values that resolve to `--api.insecure=true` only after rendering
  are out of scope for a static text scan.
- We do not chase included config files via `[providers.file]
  filename = ...`; each file is scanned independently.

## Usage

```bash
python3 detect.py path/to/traefik.yaml
python3 detect.py path/to/repo/
```

Exit codes: `0` = no findings, `1` = findings (printed to stdout),
`2` = usage error.

## Worked example

```
$ bash smoke.sh
bad=6/6 good=0/6
PASS

$ python3 detect.py examples/bad/01_compose_cli_flag.yaml
examples/bad/01_compose_cli_flag.yaml:6: traefik --api.insecure exposes API + dashboard with no auth/TLS on default :8080 (CWE-306/CWE-200): - "--api.insecure=true"

$ python3 detect.py examples/bad/02_traefik_toml.toml
examples/bad/02_traefik_toml.toml:8: traefik [api] insecure = true -> unauthenticated API+dashboard on :8080 (CWE-306/CWE-200): insecure = true

$ python3 detect.py examples/bad/03_traefik_yaml.yaml
examples/bad/03_traefik_yaml.yaml:7: traefik api: insecure: true under api: block (line 6) -> unauthenticated API+dashboard on :8080 (CWE-306/CWE-200)

$ python3 detect.py examples/good/01_api_no_insecure.toml
$ echo $?
0
```

Layout:

```
examples/bad/
  01_compose_cli_flag.yaml      # docker-compose command: --api.insecure=true
  02_traefik_toml.toml          # [api] insecure = true
  03_traefik_yaml.yaml          # api: { insecure: true }
  04_k8s_args.yaml              # k8s Deployment args: --api.insecure=true
  05_dockerfile_cmd.Dockerfile  # CMD ["traefik","--api.insecure=true",...]
  06_systemd_unit.service       # ExecStart=... --api.insecure=true
examples/good/
  01_api_no_insecure.toml       # [api] dashboard=true, insecure not set
  02_api_insecure_false.yaml    # api: { dashboard: true, insecure: false }
  03_compose_dashboard_with_auth.yaml  # router + basic-auth middleware
  04_dockerfile_explicit_false.Dockerfile  # --api.insecure=false explicit
  05_doc_comment_only.yaml      # bad pattern only in YAML comments
  06_api_block_false.toml       # [api] block with insecure=false
```
