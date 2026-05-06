# llm-output-tyk-gateway-secret-default-detector

Stdlib-only Python detector that flags **Tyk Gateway** deployments
where `secret` (the gateway's admin / management API token) is left
at the well-known sample value `352d20ee67be67f6340b4c0605b044b7`,
or any other obviously-placeholder value.

Maps to **CWE-798** (Hard-coded Credentials), **CWE-1392** (Use of
Default Credentials), **CWE-306** (Missing Authentication for
Critical Function), **CWE-1188** (Insecure Default Initialization),
OWASP **A05:2021 Security Misconfiguration**, **A07:2021
Identification & Authentication Failures**, OWASP API Security
**API2:2023 Broken Authentication**.

## Why this is a problem

Tyk's Gateway has a top-level `"secret"` field in `tyk.conf` (and a
matching `TYK_GW_SECRET` env var). That secret authenticates every
call to the **gateway's internal API**, including:

- `POST /tyk/apis/` — create / overwrite any API definition
- `POST /tyk/keys/` — mint API keys with arbitrary policies and
  quotas
- `POST /tyk/policies/` — create / overwrite policies
- `POST /tyk/reload/group` — force-reload all gateways
- `GET  /tyk/oauth/clients/*` — leak OAuth client secrets

Anyone with the gateway secret effectively owns every API behind the
gateway: they can mint full-privilege keys, drop rate limits to 0,
add upstream URLs that point at attacker-controlled backends, and
reload the cluster to apply changes immediately.

The Tyk quickstart `tyk.conf` ships with:

```json
"secret": "352d20ee67be67f6340b4c0605b044b7"
```

This value (and a small set of close variants) appears in every Tyk
getting-started repo, every "Tyk in 5 minutes" blog post, and every
docker-compose tutorial. It is one of the most-Googled API gateway
sample values in existence.

## Why LLMs ship this

The Tyk quickstart is the single most cited Tyk config snippet on
the web. Models trained on that corpus reproduce the literal hex
string verbatim. They also fall back to obvious placeholder values
(`"admin"`, `"changeme"`, `"tyk"`) when generating `tyk.conf` from
scratch, because Tyk's docs use those words as descriptions of what
the field is for.

## Heuristic

We flag, in `tyk.conf`-style JSON, YAML, env files, and shell
exports:

1. The literal Tyk quickstart secret
   `352d20ee67be67f6340b4c0605b044b7` in any `secret` /
   `node_secret` / `TYK_GW_SECRET` field.
2. Any of `secret`, `tyk`, `tyk-gw`, `changeme`, `admin`,
   `password`, `default`, empty string, or other obvious
   placeholders.
3. Any short-hex value (< 32 hex chars) in the secret field — a
   strong signal of a quickstart variant.
4. Any value shorter than 16 chars.

We do NOT flag:

- Env-var / templating references (`${TYK_GW_SECRET_FROM_VAULT}`,
  `{{ .Values.secret }}`) — assume the real value is injected from
  a secret manager at runtime.
- Generic 32+ char high-entropy values.
- Doc / README mentions of the quickstart string in prose.
- Non-Tyk JSON/YAML files that happen to have a `secret` key (we
  scope by file basename + Tyk image / config hints).

## Usage

```sh
python3 detect.py path/to/file_or_dir [more...]
```

Exit codes: `0` clean, `1` findings, `2` usage error.

## Worked example

```sh
$ cd templates/llm-output-tyk-gateway-secret-default-detector
$ ./smoke.sh
bad=4/4 good=0/4
PASS
```

## Fixtures

`examples/bad/`:

- `01_tyk.conf` — literal quickstart secret in both `secret` and
  `node_secret`.
- `02_compose_weak.yaml` — docker-compose with `TYK_GW_SECRET=admin`
  and `TYK_GW_NODE_SECRET=changeme`.
- `03_run_tyk.sh` — shell wrapper that exports `TYK_GW_SECRET=tyk-gw`.
- `04_k8s_configmap.yaml` — k8s ConfigMap embedding `tyk.conf` with
  the quickstart secret.

`examples/good/`:

- `01_tyk_strong.conf` — strong random `secret` and `node_secret`.
- `02_compose_envvar.yaml` — secrets injected via `${...}` env-var
  references from a vault.
- `03_doc_only.md` — README mentioning the quickstart string in
  prose; not a config file.
- `04_k8s_secret_strong.yaml` — k8s `Secret` with strong random
  values.

## Suggested remediation

```sh
# generate once, store in your secret manager
openssl rand -hex 32 > /run/secrets/tyk_gw_secret
openssl rand -hex 32 > /run/secrets/tyk_gw_node_secret
```

```yaml
services:
  tyk-gateway:
    image: tykio/tyk-gateway:v5.3
    environment:
      TYK_GW_SECRET_FILE: /run/secrets/tyk_gw_secret
      TYK_GW_NODE_SECRET_FILE: /run/secrets/tyk_gw_node_secret
    secrets:
      - tyk_gw_secret
      - tyk_gw_node_secret
    ports:
      - "127.0.0.1:8080:8080"   # do NOT expose the gateway admin
                                # port to the public internet
```

Front the management port with mTLS, an allow-list, or just keep it
on a private overlay. Rotate the secret on a schedule.
