# llm-output-harbor-default-admin-password-detector

Detect Harbor (container registry) configuration that ships with the upstream
default admin password `Harbor12345` left in place. LLMs frequently emit this
shape when asked to "set up Harbor with docker-compose" because it mirrors
the upstream sample `harbor.yml`. The moment such a deployment is exposed —
even on an internal network — it is an unauthenticated-equivalent registry:
anyone who can reach port 80/443 can push and pull images as `admin`.

## What bad LLM output looks like

`harbor.yml` shape:

```yaml
harbor_admin_password: Harbor12345
```

`docker-compose` env-list shape:

```yaml
environment:
  - HARBOR_ADMIN_PASSWORD=Harbor12345
```

`docker-compose` env-map shape:

```yaml
environment:
  HARBOR_ADMIN_PASSWORD: "Harbor12345"
```

Shell bootstrap shape:

```sh
export HARBOR_ADMIN_PASSWORD="Harbor12345"
```

## What good LLM output looks like

- The value is a long random secret, not the literal `Harbor12345`.
- The value is sourced from an env var (`${HARBOR_ADMIN_PASSWORD}`) populated
  by a secret store (Vault, sealed-secrets, KMS, etc.) at deploy time.
- Documentation that *mentions* the default value without actually setting it
  is fine and is not flagged.

## How the detector decides

A file is flagged if any line matches one of these literal patterns
(case-insensitive on the key, exact-match on the value `Harbor12345`):

- `harbor_admin_password: Harbor12345`             (yaml key form)
- `HARBOR_ADMIN_PASSWORD=Harbor12345`              (env / shell form)
- `- HARBOR_ADMIN_PASSWORD=Harbor12345`            (compose env-list form)
- `HARBOR_ADMIN_PASSWORD: "Harbor12345"`           (compose env-map form)

Optional surrounding double-quotes on the value are tolerated.

## Run the worked example

```sh
bash run-tests.sh
```

Expected output (per-file lines plus the tally):

```
bad=4/4 good=0/4 PASS
```

(There are 4 `bad-*.txt` fixtures and 4 `good-*.txt` fixtures; one of the
good fixtures is documentation prose, the others use a vault lookup, an env
var indirection, and a strong literal password.)

## Run against your own files

```sh
bash detect.sh path/to/harbor.yml path/to/docker-compose.yml
# or via stdin:
cat harbor.yml | bash detect.sh
```

Exit code is `0` only if every `bad-*` sample is flagged and no `good-*`
sample is flagged, making this safe to wire into CI as a defensive
misconfiguration gate for registry deployments.
