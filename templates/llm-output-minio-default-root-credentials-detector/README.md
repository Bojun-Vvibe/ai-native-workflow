# llm-output-minio-default-root-credentials-detector

Static lint that flags configurations standing up a MinIO server
with the well-known default root credentials
(`MINIO_ROOT_USER=minioadmin` /
`MINIO_ROOT_PASSWORD=minioadmin`) — or the legacy
`MINIO_ACCESS_KEY=minioadmin` / `MINIO_SECRET_KEY=minioadmin`.

`minioadmin` / `minioadmin` is the documented bootstrap default
when MinIO starts without credentials set; it is also the value
every quickstart blog, Stack Overflow answer, and LLM completion
copies verbatim. A MinIO server reachable on the network with
those credentials is a fully writable S3 endpoint and a
remote-code-execution surface via the admin API
(CWE-798: Use of Hard-coded Credentials, CWE-1392: Use of
Default Credentials).

LLM-generated `docker-compose.yml`, `.env`, and shell scripts
routinely emit:

```yaml
services:
  minio:
    image: minio/minio
    environment:
      MINIO_ROOT_USER: minioadmin
      MINIO_ROOT_PASSWORD: minioadmin
    command: server /data --console-address ":9001"
```

or:

```sh
export MINIO_ROOT_USER=minioadmin
export MINIO_ROOT_PASSWORD=minioadmin
```

This detector scans relevant text formats and flags any line that
binds one of the known MinIO credential env vars to the literal
default value.

## What it catches

- `MINIO_ROOT_USER` / `MINIO_ROOT_PASSWORD` set to `minioadmin`.
- Legacy `MINIO_ACCESS_KEY` / `MINIO_SECRET_KEY` set to
  `minioadmin`.
- Both shell-syntax (`KEY=value`, `export KEY=value`) and YAML
  syntax (`KEY: value`, `- KEY=value` in a `docker-compose`
  `environment:` list) and dotenv files.
- Quoted variants (`"minioadmin"`, `'minioadmin'`).

## CWE references

- [CWE-798](https://cwe.mitre.org/data/definitions/798.html):
  Use of Hard-coded Credentials
- [CWE-1392](https://cwe.mitre.org/data/definitions/1392.html):
  Use of Default Credentials
- [CWE-521](https://cwe.mitre.org/data/definitions/521.html):
  Weak Password Requirements

## False-positive surface

- Files containing `# minio-default-creds-allowed` are skipped
  wholesale (use for local-only smoke fixtures).
- Any non-default value (including `minioadmin1`, `changeme`,
  `${MINIO_ROOT_PASSWORD}`, or `$(openssl rand -hex 16)`) is
  accepted — this detector targets the literal default only.
- Lines beginning with `#` (shell/YAML comment) are ignored.

## Worked example

```sh
$ ./verify.sh
bad=4/4 good=0/3
PASS
```

## Files

- `detector.py` — scanner. Exit code = number of files with at least
  one finding.
- `verify.sh` — runs all `examples/bad/` and `examples/good/` and
  reports `bad=X/X good=0/Y` plus `PASS` / `FAIL`.
- `run.sh` — thin wrapper that execs `verify.sh`.
- `smoke.sh` — alias for `run.sh`, kept for harness symmetry.
- `examples/bad/` — expected to flag.
- `examples/good/` — expected to pass clean.
