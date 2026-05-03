# llm-output-pgbouncer-auth-type-trust-detector

Stdlib-only Python detector that flags **PgBouncer** configurations
which set `auth_type = trust`. Maps to **CWE-306** (missing
authentication for critical function), **CWE-1188** (insecure default
initialization of resource), and **CWE-284** (improper access control).

PgBouncer is a connection pooler that sits in front of PostgreSQL.
When `auth_type = trust` is configured in `pgbouncer.ini`, PgBouncer
accepts any client claim of identity without verifying a password —
the upstream Postgres password is then used transparently for the
real backend connection. The net effect: anyone who can reach the
PgBouncer port (often `0.0.0.0:6432` in containerised setups) can log
in as any user listed in `userlist.txt` without knowing the password.

LLMs reach for `auth_type = trust` because it is the single-line
"fix" for the common error `ERROR: password authentication failed
for user "..."` when a developer pastes a `userlist.txt` with the
wrong hash. The advice works locally, gets committed, and ships.

## Heuristic

We flag any of the following, outside `;` / `#` comment lines:

1. `auth_type = trust` directive in a `pgbouncer.ini`-style file
   (also tolerates `auth_type=trust`, with or without spaces).
2. `--auth_type=trust` (or `--auth_type trust`) on a `pgbouncer`
   command line (Dockerfile CMD/ENTRYPOINT, shell wrapper, systemd
   `ExecStart`, k8s args).
3. Exec-array form: `["pgbouncer", ..., "--auth_type", "trust"]`
   (k8s container args / docker-compose `command:` arrays).
4. Environment-variable override `PGBOUNCER_AUTH_TYPE=trust` (used
   by the popular `edoburu/pgbouncer` and `bitnami/pgbouncer`
   images that template `pgbouncer.ini` from env vars).

Each occurrence emits one finding line.

## CWE / standards

- **CWE-306**: Missing Authentication for Critical Function.
- **CWE-1188**: Insecure Default Initialization of Resource.
- **CWE-284**: Improper Access Control.
- PgBouncer docs: "`trust` — No authentication is done. Username
  must still exist in `auth_file`." — explicitly documented as the
  insecure choice; production deployments should use `scram-sha-256`
  or `md5` (legacy) or `hba` for delegated rules.

## What we accept (no false positive)

- `auth_type = scram-sha-256`, `auth_type = md5`, `auth_type = hba`,
  `auth_type = cert`, `auth_type = peer`, `auth_type = any`-with-
  comment-noting-it-is-actually-`any`-not-`trust` (we only match
  the literal `trust` value).
- Commented-out lines (`; auth_type = trust` or `# auth_type = trust`).
- Documentation / changelog mentions inside Markdown / RST files
  (we only scan config-shaped files).
- Keys that share the prefix (`auth_type_legacy`, `auth_type_v2`).

## Layout

```
detect.py            stdlib-only scanner (regex over text)
smoke.sh             runs detect.py against examples/ and asserts
examples/bad/        4 fixtures that MUST be flagged
examples/good/       3 fixtures that MUST NOT be flagged
```

## Run

```
python3 detect.py path/to/pgbouncer.ini
python3 detect.py path/to/repo
bash smoke.sh
```

Exit codes: `0` = clean, `1` = findings, `2` = usage error.

## Why this is a real LLM failure mode

`auth_type = trust` is the canonical Stack Overflow answer to
"PgBouncer rejects my connection". An LLM that has trained on those
threads will offer it as a one-line fix. The developer accepts,
PgBouncer starts, the failing test passes, the change is reviewed
on its diff (one line, looks innocuous), and the same `pgbouncer.ini`
is then templated into the staging and prod Helm charts. The
detector exists to catch the paste before it ships.
