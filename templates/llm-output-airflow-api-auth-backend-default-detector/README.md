# llm-output-airflow-api-auth-backend-default-detector

Detects Apache Airflow `airflow.cfg` configurations that leave the
stable REST API behind the legacy default
`api.auth_backend = airflow.api.auth.backend.default`, which permits
unauthenticated access to every API endpoint.

## Why this matters

Airflow's `airflow.api.auth.backend.default` backend is a no-op: every
request is treated as authenticated, with no user, no audit, and no
RBAC mapping. Combined with the default `api.enable_experimental_api`
or the stable `/api/v1/` surface, this lets any network reachable
caller trigger DAG runs, read connections (which contain database and
cloud credentials), and patch variables. The Airflow project itself
shipped this default until 2.3.0 and many older tutorials still paste
it verbatim.

LLM-generated Airflow setups frequently emit:

    [api]
    auth_backend = airflow.api.auth.backend.default

or the newer plural form:

    [api]
    auth_backends = airflow.api.auth.backend.default

This detector flags both shapes so the caller can intercept them
before they reach a scheduler that is reachable on the network.

## What it detects

For each scanned `airflow.cfg`, the detector reports a finding when:

1. The file parses as INI with an `[api]` section.
2. `auth_backend` (singular) or `auth_backends` (plural, comma list)
   contains `airflow.api.auth.backend.default`.
3. AND the web server is not bound exclusively to loopback
   (`webserver.web_server_host` unset, `0.0.0.0`, `::`, or any
   non-loopback address).

The reason string also notes when `enable_experimental_api = True`
(extra surface) and when `auth_backends` is missing entirely (which
upstream now treats as "deny", but older 2.x point releases treated
as "allow").

## CWE references

- CWE-287: Improper Authentication
- CWE-306: Missing Authentication for Critical Function
- CWE-1188: Insecure Default Initialization of Resource

## False-positive surface

- `web_server_host = 127.0.0.1` (or `localhost`, `::1`) is treated as
  a dev sandbox and ignored.
- A file that intentionally documents the default backend (e.g. a
  hardening tutorial) can be suppressed with a top-of-file comment
  `# airflow-auth-allowed`.

## Usage

    python3 detector.py path/to/airflow.cfg

Exit code: number of files with at least one finding (capped at 255).
Stdout format: `<file>:<line>:<reason>`.

Run `bash verify.sh` to execute the bundled good/bad fixtures.
