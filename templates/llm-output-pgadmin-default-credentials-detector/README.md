# llm-output-pgadmin-default-credentials-detector

Static lint that flags pgAdmin 4 container / compose / config files
(or equivalent shell / Docker / Kubernetes fragments) that ship with
the documented default-admin credentials, the well-known placeholder
email, or a hard-coded weak password literal:

- Compose / env files setting
  `PGADMIN_DEFAULT_EMAIL=admin@admin.com` (or `admin@example.com`,
  `user@domain.com`, `pgadmin@pgadmin.org`).
- Compose / env files setting
  `PGADMIN_DEFAULT_PASSWORD=admin` /
  `PGADMIN_DEFAULT_PASSWORD=pgadmin` / `=password` / `=changeme` /
  `=root` / `=postgres` / `=12345` / `=12345678`.
- Kubernetes manifests / Helm `values.yaml` with the same key/value
  pairs.
- Dockerfile `ENV PGADMIN_DEFAULT_PASSWORD admin` style lines.
- INI / `config_local.py` setting
  `MASTER_PASSWORD = 'admin'`-class literals.

## Why this matters

pgAdmin is the most common web UI for Postgres. The container image
*requires* `PGADMIN_DEFAULT_EMAIL` and `PGADMIN_DEFAULT_PASSWORD` to
boot, so there is constant pressure for "just put any value to make
it start". LLMs routinely paste the documented placeholder
`admin@admin.com` / `admin` from the upstream README directly into
production compose files, and these credentials let any reachable
caller log in as the pgAdmin super-user — which in turn stores the
connection passwords for every Postgres server the instance manages.

This detector is **orthogonal** to TLS / network-exposure detectors:
weak credentials are dangerous even on a private network because
pgAdmin is a credential vault for downstream databases, and any
internal lateral-movement path lands the attacker on every database
pgAdmin can reach.

## CWE references

- [CWE-798](https://cwe.mitre.org/data/definitions/798.html): Use of
  Hard-coded Credentials
- [CWE-521](https://cwe.mitre.org/data/definitions/521.html): Weak
  Password Requirements
- [CWE-1392](https://cwe.mitre.org/data/definitions/1392.html): Use
  of Default Credentials

## What it accepts

- Passwords sourced from env / secret refs, e.g.
  `PGADMIN_DEFAULT_PASSWORD=${PGADMIN_PW}`,
  `PGADMIN_DEFAULT_PASSWORD: ${PG_ADMIN_PW:?required}`,
  Kubernetes `valueFrom.secretKeyRef`.
- A real email address (anything not in the placeholder set) combined
  with a non-trivial password literal (length ≥ 12 and not in the
  weak-password set).
- `# pgadmin-default-allowed` opt-out marker anywhere in the file.

## False-positive surface

- Documentation prose mentioning `admin@admin.com` in a comment is
  ignored unless it is on the same line as a real
  `PGADMIN_DEFAULT_EMAIL=` assignment.
- A long random literal that happens to start with `admin` (e.g.
  `adminGx7q...`) is not flagged — only exact weak-password matches
  trigger.

## Worked example

```sh
$ ./verify.sh
bad=6/6 good=0/5
PASS
```

Per-finding output:

```sh
$ python3 detector.py examples/bad/01-compose-default-admin.yaml
examples/bad/01-compose-default-admin.yaml:7:PGADMIN_DEFAULT_EMAIL is the documented placeholder admin@admin.com
examples/bad/01-compose-default-admin.yaml:8:PGADMIN_DEFAULT_PASSWORD is the documented default 'admin'
```

## Files

- `detector.py` — scanner. Exit code = number of files with at least
  one finding.
- `verify.sh` — runs all `examples/bad/` and `examples/good/` and
  reports `bad=X/X good=0/Y` plus `PASS` / `FAIL`.
- `examples/bad/` — expected to flag.
- `examples/good/` — expected to pass clean.
