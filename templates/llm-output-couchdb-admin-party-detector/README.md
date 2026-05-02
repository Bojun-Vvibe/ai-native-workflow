# llm-output-couchdb-admin-party-detector

Flags Apache CouchDB configurations that leave the server in
**"Admin Party" mode** — no admin credentials, so any anonymous HTTP
client is implicitly an admin.

## What it catches

- `local.ini` / `default.ini` with an empty `[admins]` section
- `[admins]` with plaintext / well-known weak defaults
  (`admin`, `password`, `couchdb`, `changeme`, …)
- Dockerfile `ENV COUCHDB_PASSWORD <weak>`
- compose / `.env` / shell `COUCHDB_PASSWORD=<weak>` (including
  empty value)

## Why it's risky

In Admin Party mode every HTTP client can:

- create, drop, and replicate any database,
- read and write any document,
- change cluster-wide config via `/_node/_config`,
- start replication jobs that exfiltrate to attacker-controlled
  targets.

CouchDB was internet-scanned for this exact misconfiguration after
CVE-2017-12635 / CVE-2017-12636. Official docs:
<https://docs.couchdb.org/en/stable/setup/single-node.html>.

Maps to **CWE-306** (Missing Authentication for Critical Function),
**CWE-1188** (Insecure Default Initialization of Resource),
**CWE-732** (Incorrect Permission Assignment), **CWE-798** (Use of
Hard-coded Credentials), **OWASP A05:2021**, **OWASP A07:2021**.

## Why LLMs ship this

Quickstart blog posts say `docker run -p 5984:5984 couchdb` with no
admin env vars, or hard-code `COUCHDB_PASSWORD=password`. Models
copy those snippets into production manifests.

## Usage

```bash
python3 detect.py path/to/config-or-dir
```

Exit codes:

- `0` — clean
- `1` — at least one finding
- `2` — usage error

Stdlib-only. Walks directories and scans `*.ini`, `*.yaml`, `*.yml`,
`*.env`, `*.sh`, `*.bash`, `*.service`, `Dockerfile*`,
`docker-compose.*`.

## Smoke test

```bash
./smoke.sh
# bad=N/N good=0/M
# PASS
```

## What it does NOT flag

- `[admins]` blocks containing **hashed** values
  (`-pbkdf2-…`, `-hashed-…`).
- `COUCHDB_PASSWORD` references that point to a secret manager
  (`${SECRET_PASSWORD}`, `$(cat /run/secrets/…)`) — the variable
  expansion is not a known weak literal.
- Anonymous client `curl` traffic — server-side config only.
