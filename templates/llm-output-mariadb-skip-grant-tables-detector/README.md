# llm-output-mariadb-skip-grant-tables-detector

Detect MariaDB / MySQL configuration and start-up snippets that disable the
privilege system or render it useless. The classic LLM failure mode here is
the "I forgot the root password, what do I do?" answer: the model emits a
recipe that adds `skip-grant-tables` to `my.cnf`, ships a Dockerfile whose
`CMD` is `mysqld --skip-grant-tables --skip-networking=0`, or sets
`MYSQL_ALLOW_EMPTY_PASSWORD=yes` in a compose env file. Each of these turns
every connection into an effectively-root session with no authentication.

## What bad LLM output looks like

`my.cnf` with the privilege system disabled and the daemon listening on all
interfaces:

```
[mysqld]
skip-grant-tables
bind-address=0.0.0.0
```

A Dockerfile that bakes `--skip-grant-tables` into the default command and
explicitly re-enables networking:

```dockerfile
CMD ["mariadbd", "--user=mysql", "--skip-grant-tables", "--skip-networking=0"]
```

A docker-compose env file that opts into empty-password mode:

```
MYSQL_ALLOW_EMPTY_PASSWORD=yes
```

A bootstrap script that re-grants the world to `root`:

```sql
GRANT ALL PRIVILEGES ON *.* TO 'root'@'%' IDENTIFIED BY 'root' WITH GRANT OPTION;
```

## What good LLM output looks like

- `my.cnf` keeps the privilege system on, binds to `127.0.0.1`, and uses
  `--init-file` for one-shot password resets under a maintenance window.
- Dockerfile `CMD` carries `--require-secure-transport=ON` and no
  `--skip-grant-tables`.
- Container env vars use `MARIADB_ROOT_PASSWORD_FILE` / `MARIADB_RANDOM_ROOT_PASSWORD=no`
  with secrets mounted via the orchestrator.
- Bootstrap SQL creates a least-privilege application user from a secret-
  store value, scoped to a specific subnet (`'app'@'10.%'`).

## Run the smoke test

```sh
bash detect.sh samples/bad/* samples/good/*
```

Expected output:

```
BAD  samples/bad/bootstrap_grant_all_root.sql
BAD  samples/bad/compose_env_allow_empty_password.dotenv-example.txt
BAD  samples/bad/dockerfile_cmd_skip_grant.Dockerfile
BAD  samples/bad/my_cnf_skip_grant.cnf
GOOD samples/good/bootstrap_least_privilege.sql
GOOD samples/good/compose_env_secret_files.dotenv-example.txt
GOOD samples/good/dockerfile_cmd_normal.Dockerfile
GOOD samples/good/my_cnf_secure.cnf
bad=4/4 good=0/4 PASS
```

Exit status is `0` only when every bad sample is flagged and zero good
samples are flagged.

## Detector rules

1. `skip-grant-tables` (or `skip_grant_tables`) appearing as a `my.cnf`
   directive — bare line, optionally `=1`/`=true`/`=ON`/`=yes`.
2. A `mysqld` or `mariadbd` invocation on the same line as
   `--skip-grant-tables` — covers Dockerfile `CMD`/`RUN`,
   `docker-compose` `command:` entries, and entrypoint scripts.
3. `MYSQL_ALLOW_EMPTY_PASSWORD` or `MARIADB_ALLOW_EMPTY[_ROOT]_PASSWORD`
   set to `yes`/`true`/`1` (env files, compose `environment:` lists,
   Dockerfile `ENV` lines).
4. SQL of the form `GRANT ALL [PRIVILEGES] ON *.* TO 'root'@'<anything>'
   IDENTIFIED BY '<empty|root|password|admin|123456|mysql|mariadb>'` —
   collapsed across newlines so multi-line `GRANT` statements still match.

Shell `#` comments and SQL `-- ` comments are stripped before matching.
