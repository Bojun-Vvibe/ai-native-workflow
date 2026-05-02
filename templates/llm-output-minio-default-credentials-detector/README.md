# llm-output-minio-default-credentials-detector

Flags configurations that run a MinIO (S3-compatible object store)
server with the **default `minioadmin` / `minioadmin` root
credentials** -- or any other well-known weak value (`admin`,
`password`, `12345`, empty string, etc.) for the root access key /
secret env vars.

## Why this matters

MinIO's first-boot defaults are documented as `minioadmin` for both
`MINIO_ROOT_USER` and `MINIO_ROOT_PASSWORD` (legacy
`MINIO_ACCESS_KEY` / `MINIO_SECRET_KEY`). Leaving them unchanged in
production gives anonymous internet callers full bucket
read/write/delete -- and, via admin policies and event
notifications, frequently a path to host pivot.

Maps to:

- **CWE-798** Use of Hard-coded Credentials
- **CWE-1188** Insecure Default Initialization of Resource
- **OWASP A07:2021** Identification and Authentication Failures

## Why LLMs ship this

Quickstart docs and Docker examples show:

```
docker run -e MINIO_ROOT_USER=minioadmin \
           -e MINIO_ROOT_PASSWORD=minioadmin \
           quay.io/minio/minio server /data
```

Models lift those literals into production compose / Helm /
Dockerfile / CI scripts.

## Heuristic

Flags any of these set to a known-weak literal value
(case-insensitive `minioadmin`, `admin`, `password`, `changeme`,
`minio`, `minio123`, `12345`, …, or empty string):

- `MINIO_ROOT_USER` / `MINIO_ROOT_PASSWORD`
- `MINIO_ACCESS_KEY` / `MINIO_SECRET_KEY`
- Helm-style `rootUser:` / `rootPassword:` / `accessKey:` /
  `secretKey:`
- `mc alias set <name> <url> <user> <pass>` shell commands

Skips values that look like env interpolation (`${...}`, `$(...)`,
`{{ ... }}`, heredoc).

## Usage

```
python3 detect.py path/to/docker-compose.yml
python3 detect.py path/to/repo/   # walks dir
```

Exit codes: 0 = clean, 1 = findings, 2 = usage error.

## Smoke (verified)

```
$ bash smoke.sh
bad=5/5 good=0/3
PASS
```

Sample finding:

```
examples/bad/02-docker-compose.yml:7: MINIO_ROOT_USER=minioadmin
  (weak/default MinIO credential, CWE-798/CWE-1188): MINIO_ROOT_USER: minioadmin
examples/bad/05-mc-alias.sh:3: `mc alias set` uses weak/default
  MinIO credentials (minioadmin/minioadmin) -> CWE-798
```

## Layout

```
detect.py                # stdlib-only, walks dirs
smoke.sh                 # end-to-end harness
examples/bad/            # 5 misconfigured: shell, compose, Dockerfile, helm, mc
examples/good/           # 3 properly templated configs
```
