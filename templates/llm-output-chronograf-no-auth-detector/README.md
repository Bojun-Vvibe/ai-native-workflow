# llm-output-chronograf-no-auth-detector

Stdlib-only Python detector that flags **Chronograf** (InfluxData's UI
for InfluxDB / Kapacitor) launched on a non-loopback bind address with
**no OAuth / OIDC provider configured**. Maps to **CWE-306** (missing
authentication for critical function), **CWE-284** (improper access
control), and **CWE-1188** (insecure default initialization).

Chronograf has **no authentication out of the box**. The only supported
multi-user auth is via an external OAuth provider (GitHub, Google,
Heroku, Auth0, generic OIDC). Without it, anyone who can reach the
HTTP port (default `:8888`) can:

- Read every dashboard, source, and alert rule.
- Add new InfluxDB / Kapacitor sources, pivoting onto upstream DBs.
- Run arbitrary InfluxQL / Flux queries against connected sources.
- Edit / delete Kapacitor TICKscripts (RCE on the alerting tier).

LLMs ship this misconfig because the upstream quickstart is a single
`docker run -p 8888:8888 chronograf` line and most Helm / compose
examples don't include the OAuth env vars.

## Heuristic

We scan for invocations of the `chronograf` binary / image and look at
the surrounding env / args block. Auth is considered configured when
BOTH are present (locally or globally in the same file):

- A token signing secret: `TOKEN_SECRET=` env or `--token-secret` flag
  (or `JWKS_URL` for OIDC discovery).
- A provider client-id: `GH_CLIENT_ID`, `GOOGLE_CLIENT_ID`,
  `GENERIC_CLIENT_ID`, `HEROKU_CLIENT_ID`, `AUTH0_CLIENT_ID` (or the
  matching `--*-client-id` flags).

Loopback binds (`--host 127.0.0.1`, `localhost`, `[::1]`) are exempt.
If `--host` / `HOST` is unset, Chronograf defaults to `0.0.0.0`, which
we treat as public.

## CWE / standards

- **CWE-306**: Missing Authentication for Critical Function.
- **CWE-284**: Improper Access Control.
- **CWE-1188**: Insecure Default Initialization of Resource.
- Chronograf docs: "Chronograf does not require authentication by
  default. To enable, configure an OAuth 2.0 provider."

## What we accept (no false positive)

- `TOKEN_SECRET=...` plus any `*_CLIENT_ID=...` env pair.
- `--token-secret` plus any `--*-client-id` flag.
- Loopback-only `--host 127.0.0.1` / `HOST=localhost`.
- File-global env block hoisted out of the service definition.

## What we flag

- Bare `docker run chronograf` with no env vars.
- `chronograf` binary in a systemd unit with no OAuth env.
- compose / k8s manifests where `chronograf` has no `*_CLIENT_ID`
  in the file at all.
- `chronograf --host 0.0.0.0` with no auth flags.

## Limits / known false negatives

- We don't validate the OAuth secret strength or that the configured
  provider URL is reachable.
- A stray `TOKEN_SECRET` in a comment is ignored (we strip `#`
  comments) but a hoisted env block in the same file suppresses the
  finding even if it actually targets a different service.
- We don't check `--public-url`, `--inactivity-duration`, or RBAC
  role mapping.

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
bad=4/4 good=0/4
PASS
```

Layout:

```
examples/bad/
  01_docker_run.Dockerfile      # bare `chronograf` no env
  02_compose_default.yaml       # compose with no OAuth env
  03_systemd.service            # chronograf --host 0.0.0.0 no flags
  04_k8s_deploy.yaml            # k8s Deployment, no OAuth env
examples/good/
  01_github_oauth.yaml          # TOKEN_SECRET + GH_CLIENT_ID
  02_loopback.service           # --host 127.0.0.1
  03_auth0_compose.yaml         # AUTH0_CLIENT_ID + TOKEN_SECRET
  04_generic_oidc.Dockerfile    # GENERIC_CLIENT_ID + TOKEN_SECRET
```
