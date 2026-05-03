# llm-output-postgrest-anon-role-superuser-detector

Stdlib-only Python detector that flags **PostgREST** configurations
which set `db-anon-role` to a Postgres role with broad privileges
(`postgres`, `postgrest`, `admin`, `root`, `superuser`, or any role
that the same file just `GRANT`-ed `ALL PRIVILEGES` /
`CREATE ROLE ... SUPERUSER` to). Maps to **CWE-269** (improper
privilege management), **CWE-732** (incorrect permission assignment
for critical resource), and **CWE-284** (improper access control).

PostgREST authenticates JWT-less requests as the `db-anon-role`. If
that role is the database superuser — or any role with `BYPASSRLS`,
`CREATEROLE`, `CREATEDB`, or table-level `ALL` on the public schema —
then every anonymous HTTP caller has the same powers as a logged-in
DBA, including reading every table and (via `pg_read_server_files`,
`COPY ... PROGRAM`, or untrusted PL/pgSQL) achieving RCE on the host.

The intended pattern is to create a dedicated `web_anon` role with
`NOLOGIN`, no inherited privileges, and explicit `GRANT SELECT` on
exactly the tables/views you mean to expose.

## Heuristic

We flag any of the following, outside `--` / `#` comment lines:

1. PostgREST config: `db-anon-role = "postgres"` (or `postgres`,
   `postgrest`, `admin`, `root`, `dba`, `superuser`) in `.conf` /
   `postgrest.conf` style files.
2. Env var: `PGRST_DB_ANON_ROLE=postgres` (any of the above values),
   in `.env` files, shell scripts, Dockerfile `ENV`, or
   docker-compose / k8s `environment:` blocks.
3. SQL bootstrap that grants superuser / bypassrls to the configured
   anon role: `ALTER ROLE web_anon SUPERUSER`,
   `ALTER ROLE web_anon BYPASSRLS`, or
   `GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO web_anon`.
4. CLI flag: `postgrest --db-anon-role postgres` (or any forbidden role).

Each occurrence emits one finding line.

## CWE / standards

- **CWE-269**: Improper Privilege Management.
- **CWE-732**: Incorrect Permission Assignment for Critical Resource.
- **CWE-284**: Improper Access Control.
- PostgREST docs: "The `db-anon-role` should be a role with the
  minimum privileges necessary."

## What we accept (no false positive)

- `db-anon-role = "web_anon"` (or any role name not on the deny list)
  paired with explicit narrow grants.
- Commented-out / documentation lines.
- SQL that creates the anon role with `NOLOGIN` and grants only
  `USAGE` on schema and `SELECT` on specific tables.

## Layout

```
detect.py            stdlib-only scanner
smoke.sh             runs detect.py against examples/ and asserts
examples/bad/        4 fixtures that MUST be flagged
examples/good/       3 fixtures that MUST NOT be flagged
```

## Run

```
python3 detect.py path/to/postgrest.conf
python3 detect.py path/to/repo
bash smoke.sh
```

Exit codes: `0` = clean, `1` = findings, `2` = usage error.

## Why this is a real LLM failure mode

Developers asking an LLM "give me a one-file PostgREST setup so I can
hit my Postgres tables over HTTP" frequently get back a config that
sets `db-anon-role = "postgres"` because that role definitely exists
and avoids `42501` permission errors. Anyone who can reach port 3000
then has superuser SQL on the database. This detector exists to flag
those snippets before they ship.
