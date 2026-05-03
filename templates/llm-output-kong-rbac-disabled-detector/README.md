# llm-output-kong-rbac-disabled-detector

Stdlib-only Python detector that flags **Kong Gateway** /
**Kong Enterprise** deployments whose Admin API is configured with
**RBAC disabled** (`enforce_rbac = off`, `KONG_ENFORCE_RBAC=off`,
`enterprise.rbac.enabled=false`), or whose Admin API is bound to a
public address with no RBAC and no GUI-auth strategy.

Maps to **CWE-306** (missing authentication for critical function)
and **CWE-732** (incorrect permission assignment for critical
resource).

## Why this matters

Kong's Admin API (default `:8001` HTTP, `:8444` HTTPS) is the
**control plane**: anyone who reaches it can add routes, attach
plugins, re-route traffic, and read or modify upstream credentials.
Kong's `enforce_rbac` flag (OSS edition since 2.x; Enterprise full
RBAC) ships with `enforce_rbac = off` in `kong.conf.default`.

LLMs nevertheless emit:

```bash
docker run -e "KONG_ADMIN_LISTEN=0.0.0.0:8001" kong:3.7
```

```ini
admin_listen = 0.0.0.0:8001
enforce_rbac = off
```

```bash
helm install kong kong/kong --set enterprise.rbac.enabled=false
```

…and ship it onto a network reachable from outside the trust
boundary. The result is an unauthenticated, fully privileged
control plane.

Upstream reference (v3.x, current as of this template):

- <https://github.com/Kong/kong> (`kong.conf.default`,
  `--enforce-rbac`)
- <https://docs.konghq.com/gateway/latest/kong-enterprise/rbac/>
- <https://docs.konghq.com/gateway/latest/admin-api/>

## Heuristic

A file is "kong-related" if it mentions a `kong:` / `kong/kong-gateway:`
image tag, or any of the env / config keys
`KONG_ADMIN_LISTEN`, `KONG_ENFORCE_RBAC`, `KONG_ADMIN_GUI_AUTH`,
`admin_listen`, `enforce_rbac`.

Inside such a file, outside `#` / `//` comments, we flag:

1. Explicit RBAC off:
   - `enforce_rbac = off` in `kong.conf`
   - `KONG_ENFORCE_RBAC: "off"` (env var)
   - `--set enterprise.rbac.enabled=false` / `--set enforce_rbac=off`
     (Helm)
2. Admin API publicly bound (`0.0.0.0:<port>`) when:
   - the file does NOT also enable RBAC
     (`enforce_rbac = on` / `KONG_ENFORCE_RBAC=on` /
     `enterprise.rbac.enabled=true`), AND
   - the file does NOT set `KONG_ADMIN_GUI_AUTH` to a real strategy
     (`basic-auth`, `key-auth`, `ldap-auth-advanced`,
     `openid-connect`).

Each occurrence emits one finding line.

## What we accept (no false positive)

- `admin_listen = 127.0.0.1:8001` with `enforce_rbac = on`.
- Admin API on `0.0.0.0` with `KONG_ENFORCE_RBAC=on` and
  `KONG_ADMIN_GUI_AUTH=basic-auth`.
- README / runbook files that mention the bad shape only inside
  `#` / `//` comments.

## What we flag

- `kong.conf` with `enforce_rbac = off`.
- docker-compose env `KONG_ENFORCE_RBAC: "off"`.
- k8s Deployment env `KONG_ADMIN_LISTEN=0.0.0.0:8001` with no RBAC
  and no GUI auth strategy.
- `helm install ... --set enterprise.rbac.enabled=false`.

## Limits / known false negatives

- We do not parse Helm values files line-by-line into a tree; we
  match `enabled: true` only inline or in a 2-line `rbac:\n  enabled:
  true` block.
- We do not inspect NetworkPolicy / firewall rules that might
  re-restrict a public Admin API.
- We do not validate the contents of plugins like `key-auth`
  applied to the Admin API via routes; if a Route+Plugin protects
  `/`, this detector will still flag the bind. Treat findings as
  "prove the wrapper is doing the work."

## Usage

```bash
python3 detect.py path/to/repo/
python3 detect.py kong.conf docker-compose.yaml
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
  01_kong.conf                  # admin_listen=0.0.0.0 + enforce_rbac=off
  02_compose_env_off.yaml       # KONG_ENFORCE_RBAC: "off"
  03_admin_public_no_rbac.yaml  # 0.0.0.0:8001, no RBAC, no GUI auth
  04_helm_set_off.sh            # helm --set enterprise.rbac.enabled=false
examples/good/
  01_kong.conf                  # 127.0.0.1 + enforce_rbac=on
  02_admin_public_with_rbac.yaml # 0.0.0.0 + RBAC on + basic-auth
  03_doc_only.conf              # bad form only in comments
```
