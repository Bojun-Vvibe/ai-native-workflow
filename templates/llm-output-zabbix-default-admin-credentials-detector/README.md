# llm-output-zabbix-default-admin-credentials-detector

Static lint that flags Zabbix frontend / server bootstrap configurations
shipping the well-known default Super Admin credential `Admin` /
`zabbix` (or other trivial variants) in deployable artifacts.

The Zabbix web frontend ships with a hard-coded factory account
`Admin` (capital A) whose initial password is the literal string
`zabbix`. Every Zabbix install since 1.x has used these defaults, and
they are documented as the post-install starting point. LLM output
routinely copies the documented bootstrap password into production
docker-compose files, Helm values, k8s Secrets, or `.env` files. The
frontend is reachable on the same listener that serves dashboards
(`/zabbix/index.php`), so a leaked default credential is a full
monitoring-system takeover — every host, every script item, every
discovery action.

## Variables / fields checked

- Docker image envs:
  - `ZBX_SERVER_USER` / `ZBX_SERVER_PASSWORD` (server-side script auth)
  - `ZABBIX_USER` / `ZABBIX_PASSWORD`
  - `MYSQL_USER` / `MYSQL_PASSWORD` paired with `MYSQL_DATABASE=zabbix`
    when the password value matches a trivial set
- Frontend bootstrap envs:
  - `PHP_ZBX_USER` / `PHP_ZBX_PASSWORD`
  - `ZBX_FRONTEND_USER` / `ZBX_FRONTEND_PASSWORD`
- API bootstrap script literals:
  - `user.login` JSON-RPC payloads with `"user": "Admin"` and
    `"password": "zabbix"` (or trivial)
- CLI flags / shell exports:
  - `--zabbix-user`, `--zabbix-password`

## File shapes recognized

Dockerfile `ENV` / `ARG`, `docker-compose.yml` `environment:`,
Kubernetes manifest `env:` list (split-line `name:` / `value:`),
Secret `stringData:`, `.env` files, shell `export` /
systemd `EnvironmentFile=` lines, JSON literals in `.json` / `.sh`.

## Why this matters

The `Admin` account in Zabbix has full Super Admin role. With it an
attacker can:

- Add hosts and run remote commands via script items (RCE on monitored
  agents that allow `EnableRemoteCommands=1`).
- Read every metric ever collected, including credential metadata if
  scripts log it.
- Pivot to the database via `mediatype` webhook scripts.

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
- Files containing the marker `# zabbix-default-admin-allowed`
  (e.g. ephemeral test fixtures, ephemeral CI containers).
- Non-trivial passwords (anything outside the canonical default set).
- A trivial username on its own (`Admin`) without a paired trivial
  password.

## False-positive surface

- The username field literally being `Admin` is fine on its own.
  The detector only fires when a paired password key is also trivial
  (or when the password key alone is trivial regardless of username).

## Worked example

```sh
$ ./verify.sh
bad=6/6 good=4/4
PASS
```

Per-finding output:

```sh
$ python3 detector.py examples/bad/01-compose.yml
examples/bad/01-compose.yml:9:ZBX_SERVER_PASSWORD set to trivial/default value 'zabbix' — Zabbix Super Admin password must be unique per environment
```

## Files

- `detector.py` — scanner. Exit code = number of files with at least
  one finding (capped at 255).
- `verify.sh` — runs all `examples/bad/` and `examples/good/` and
  reports `bad=X/X good=0/Y` plus `PASS` / `FAIL`.
- `examples/bad/` — expected to flag (≥5 cases).
- `examples/good/` — expected to pass clean (≥3 cases).
