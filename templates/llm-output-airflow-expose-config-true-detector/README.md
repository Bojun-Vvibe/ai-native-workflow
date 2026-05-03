# llm-output-airflow-expose-config-true-detector

Static lint that flags Apache Airflow configurations and environment
files where the `[webserver] expose_config` knob is enabled, exposing
the entire `airflow.cfg` (including the Fernet key, SQL Alchemy
connection string, broker URL, secrets backend config, etc.) over
the webserver `/config` endpoint to anyone who can hit the UI.

## Background

Airflow's webserver ships a `/config` view that renders the in-memory
`airflow.cfg`. By default this view is disabled (`expose_config = False`)
because the rendered config contains the Fernet key used to encrypt
every Connection password and Variable, plus the metadata DB URL,
result/broker URLs, and secrets-backend kwargs.

Enabling `expose_config = True` (or the equivalent
`AIRFLOW__WEBSERVER__EXPOSE_CONFIG=True` env var) is a documented
foot-gun: any authenticated user — and on misconfigured deployments,
anonymous users — can read the entire config blob from the browser
or via the REST API. Combined with default admin credentials or an
exposed webserver this is a one-shot full-credential exfiltration.

LLM-generated `airflow.cfg` / Helm values / docker-compose snippets
routinely set `expose_config = True` "for debugging" and the value
sticks in production.

## CWE

- [CWE-200: Exposure of Sensitive Information to an Unauthorized Actor](https://cwe.mitre.org/data/definitions/200.html)
- Related: [CWE-497: Exposure of Sensitive System Information to an Unauthorized Control Sphere](https://cwe.mitre.org/data/definitions/497.html)

## What it catches

- `expose_config = True` (or `true`, `1`, `yes`, `on`) under `[webserver]`
  in `airflow.cfg`.
- `expose_config = non-sensitive-only` is **also** flagged with a softer
  message — that mode still leaks the broker URL, scheduler config,
  etc., and is rarely what the operator actually wants.
- `AIRFLOW__WEBSERVER__EXPOSE_CONFIG=True` in shell scripts,
  Dockerfiles, `docker-compose.yml`, `.env`, Helm values, k8s
  ConfigMaps, etc.
- Helm-style `webserver.exposeConfig: true` values.

## What it does *not* catch

This is a static check on config text. It does not introspect a
running Airflow instance, and it does not flag custom plugins that
re-implement a similar config endpoint.

## Remediation

- Set `expose_config = False` (the Airflow default).
- If you genuinely need to inspect config in a running cluster, use
  `airflow config list` from a shell on the scheduler host instead
  of exposing the value over HTTP.
- Rotate the Fernet key, DB password, and any secrets-backend
  credentials if `expose_config = True` was ever live in production —
  assume they're compromised.

## Suppression

Add the comment marker `airflow-expose-config-allowed` anywhere in the
file to suppress findings (intended for known-test fixtures, sandbox
demos that contain no real credentials, etc.).

## Usage

```sh
python3 detector.py path/to/airflow.cfg path/to/.env
```

Exit code is the number of findings. `0` means clean.

## Verify

```sh
bash verify.sh
```

Smoke-test output on a clean tree:

```
bad=4/4 good=0/3
PASS
```

Every `examples/bad/*` fixture fires at least one finding; every
`examples/good/*` fixture is clean.
