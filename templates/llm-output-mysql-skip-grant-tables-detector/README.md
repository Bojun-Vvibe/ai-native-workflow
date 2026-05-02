# llm-output-mysql-skip-grant-tables-detector

Detect MySQL / MariaDB configuration, container, systemd, and SQL bootstrap
snippets that disable the entire privilege system via `--skip-grant-tables`
(a.k.a. `skip_grant_tables`). LLMs reach for this flag whenever they're asked
"how do I reset the root password" or "the migration script can't authenticate"
— and the reset/recovery procedure leaks into the long-lived config, leaving
a server where any client that can reach port 3306 logs in as `root` with no
password and no GRANT checks.

## What bad LLM output looks like

`my.cnf` with the flag enabled in the persistent config:

```
[mysqld]
skip-grant-tables
bind-address=0.0.0.0
```

A docker / systemd command line that bakes it in:

```
mysqld --skip_grant_tables --user=mysql
docker run mysql:8 --skip-grant-tables ...
```

A bootstrap SQL script that flips the global at runtime:

```sql
SET GLOBAL skip_grant_tables = 1;
```

## What good LLM output looks like

The flag is absent, or only mentioned in commented-out emergency-recovery
docs, and authentication plugins are configured normally:

```
[mysqld]
bind-address=127.0.0.1
default_authentication_plugin=caching_sha2_password
# skip-grant-tables  ← only used interactively for root password recovery
```

Containers pass real credentials via secrets:

```
docker run -e MYSQL_ROOT_PASSWORD_FILE=/run/secrets/mysql_root mysql:8
```

## Run the smoke test

```sh
bash detect.sh samples/bad/* samples/good/*
```

Expected output:

```
BAD  samples/bad/docker_compose_cmdline.sh
BAD  samples/bad/init_sql_runtime.sql
BAD  samples/bad/my_cnf_skip_grant.cnf
BAD  samples/bad/systemd_unit.service
GOOD samples/good/docker_compose_safe.sh
GOOD samples/good/my_cnf_normal.cnf
GOOD samples/good/recovery_doc.md
bad=4/4 good=0/3 PASS
```

Exit status is `0` only when every bad sample is flagged and zero good samples
are flagged.

## Detector rules

1. An uncommented `skip-grant-tables` (or `skip_grant_tables`) line in a
   config file, optionally `=1|true|on`.
2. A `--skip-grant-tables` / `--skip_grant_tables` command-line flag in a
   shell script, Dockerfile, compose file, or systemd unit.
3. A SQL statement of the form `SET GLOBAL skip_grant_tables = ...` —
   covers init scripts that try to disable auth at runtime.
