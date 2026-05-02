# llm-output-mlflow-server-no-auth-detector

Static lint that flags `mlflow server` / `mlflow ui` invocations bound
to a non-loopback interface without the basic-auth app enabled.

MLflow's tracking server has historically shipped with **no built-in
authentication**. The basic-auth plugin (`--app-name basic-auth`)
landed in MLflow 2.5+, and even then it must be opted into. LLM-paste
Dockerfiles, `docker-compose.yml`, systemd units, and Kubernetes
manifests routinely contain:

```sh
mlflow server --host 0.0.0.0 --port 5000 \
  --backend-store-uri sqlite:///mlflow.db \
  --default-artifact-root /mlruns
```

That endpoint exposes:

- The full **artifact store** (model binaries, datasets) for
  download.
- `/api/2.0/mlflow/runs/log-artifact` write endpoints (model
  poisoning).
- The historical `/files` endpoint (path traversal CVE-2023-1177
  family).
- Database introspection via the tracking API.

This detector flags those shapes in shell scripts, Dockerfiles,
compose files, systemd units, and Kubernetes pod specs.

## What it catches

- `mlflow server` or `mlflow ui` with `--host 0.0.0.0`, `--host ::`,
  or `-h 0.0.0.0`.
- `mlflow server` with no `--host` flag inside a Dockerfile `CMD` /
  `ENTRYPOINT` (the project default in container contexts almost
  always intends external bind via published port).
- Compose / k8s entries that exec `mlflow server ...` and publish
  port 5000 without the basic-auth app.
- Auth-bypass shapes such as `--app-name basic-auth` overridden by
  `MLFLOW_AUTH_CONFIG_PATH=/dev/null` or empty.

## What is treated as safe

- `--host 127.0.0.1` / `--host localhost` / `--host ::1`.
- Presence of `--app-name basic-auth` (or `--app-name` pointing at a
  custom auth plugin name) on the same logical command.
- Reverse-proxy auth shape: a sibling line containing `nginx`,
  `traefik`, `caddy`, or `oauth2-proxy` in the same file is a hint
  but not relied on alone — explicit suppression is required:
  `# mlflow-auth-external`.

## CWE references

- [CWE-306](https://cwe.mitre.org/data/definitions/306.html): Missing
  Authentication for Critical Function
- [CWE-284](https://cwe.mitre.org/data/definitions/284.html): Improper
  Access Control

## False-positive surface

- Local dev loops where the server lives behind `localhost`-only
  port forwarding. Suppress with `# mlflow-auth-external` anywhere
  in the file.
- Hosted MLflow (Databricks, SageMaker) where auth is enforced by
  the platform and `mlflow server` is never run by the user — those
  files won't contain `mlflow server` invocations at all.

## Verified

```
$ ./verify.sh
bad=4/4 good=0/4
PASS
```

Per-file output (sample):

```
examples/bad/01-compose.yml:5:mlflow server bound to non-loopback (host=0.0.0.0) without --app-name basic-auth
examples/bad/02-Dockerfile:9:mlflow server CMD without --host (defaults to all interfaces) and no --app-name basic-auth
examples/bad/03-run.sh:3:mlflow ui bound to non-loopback (host=::) without --app-name basic-auth
examples/bad/04-systemd.service:8:mlflow server bound to non-loopback (host=0.0.0.0) without --app-name basic-auth
```

## Files

- `detector.py` — scanner. Exit code = number of files with at least
  one finding (capped at 255).
- `verify.sh` — runs all `examples/bad/` and `examples/good/` and
  reports `bad=X/X good=Y/Z` plus `PASS` / `FAIL`.
- `examples/bad/` — expected to flag.
- `examples/good/` — expected to pass clean.
