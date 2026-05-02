# llm-output-rundeck-default-admin-credentials-detector

Static lint that flags Rundeck bootstrap configurations shipping the
well-known default admin credential `admin:admin` in deployable
artifacts — typically the JAAS `realm.properties` file, the official
Docker image's `RUNDECK_ADMIN_PASSWORD` env, or seed scripts that
create the bootstrap admin account.

The official `rundeck/rundeck` Docker image and the upstream Rundeck
distribution both ship with `admin / admin` as the documented
bootstrap credential. The `realm.properties` file under
`server/config/` is the JAAS user store, and the literal entry
`admin: admin, user, admin` is the documented starting point.
LLM output routinely copies this verbatim into production-shaped
artifacts (Dockerfile, docker-compose, Kubernetes Secrets, Helm
values). The Rundeck UI and API are reachable on the same listener
that runs job executions; a leaked default credential is a remote
job-execution surface — every node, every script, every secret
reference.

## Variables / fields checked

- Docker image envs:
  - `RUNDECK_ADMIN_PASSWORD`
  - `RD_ADMIN_PASSWORD`
- `realm.properties` (JAAS file-based auth) entries shaped as
  `username: password, role[, role...]`:
  - The literal user `admin` whose password is in the trivial set.
  - Any user whose password equals one of the canonical defaults
    `{admin, password, changeme, rundeck, root, ...}`.
- `framework.properties` / `rundeck-config.properties`:
  - `framework.server.password=admin` (server-to-server auth)
- API bootstrap shell scripts:
  - `curl -u admin:admin http://.../api/...`
  - `--user admin:admin`

## File shapes recognized

`*.properties` (JAAS / framework), Dockerfile `ENV` / `ARG`,
`docker-compose.yml` `environment:`, Kubernetes manifest `env:` list
(split-line `name:` / `value:`), Secret `stringData:`, `.env` files,
shell `export` lines, shell `curl -u user:pass` calls.

## Why this matters

Rundeck's admin role grants:

- Execute arbitrary jobs against any configured node (SSH/WinRM RCE
  surface — `Execution` ACL is permissive by default for the `admin`
  group).
- Read and modify the project keystore (stored API tokens, SSH keys,
  database passwords used by jobs).
- Define new jobs that run shell commands on the Rundeck server itself
  (local-node executor).

A leaked default credential maps to remote command execution on
every node Rundeck manages.

## CWE references

- [CWE-798](https://cwe.mitre.org/data/definitions/798.html): Use of
  Hard-coded Credentials
- [CWE-1392](https://cwe.mitre.org/data/definitions/1392.html): Use of
  Default Credentials
- [CWE-521](https://cwe.mitre.org/data/definitions/521.html): Weak
  Password Requirements

## What it accepts (no findings)

- Values that look like unresolved templating: `${...}`, `$(...)`,
  `<<TOKEN>>`, `{{ .Values.x }}`, `%ENV%`.
- Files containing the marker `# rundeck-default-admin-allowed`.
- Non-trivial passwords.
- Hashed JAAS entries (values starting with `MD5:`, `CRYPT:`,
  `OBF:`) — these are pre-hashed and not the cleartext default.

## False-positive surface

- The `admin` username on its own is fine; the detector requires a
  trivial cleartext password value to fire.

## Worked example

```sh
$ ./verify.sh
bad=6/6 good=4/4
PASS
```

Per-finding output:

```sh
$ python3 detector.py examples/bad/01-realm.properties
examples/bad/01-realm.properties:3:realm.properties user 'admin' uses trivial password 'admin' — Rundeck bootstrap admin must be rotated
```

## Files

- `detector.py` — scanner. Exit code = number of files with at least
  one finding (capped at 255).
- `verify.sh` — runs all `examples/bad/` and `examples/good/` and
  reports `bad=X/X good=0/Y` plus `PASS` / `FAIL`.
- `examples/bad/` — expected to flag (≥5 cases).
- `examples/good/` — expected to pass clean (≥3 cases).
