# llm-output-guacamole-default-guacadmin-credentials-detector

Stdlib-only Python detector that flags **Apache Guacamole**
(clientless remote-desktop gateway, [guacamole.apache.org](https://guacamole.apache.org))
deployments where the upstream `guacadmin` / `guacadmin` bootstrap
admin from `guacamole-auth-jdbc` `initdb.sql` is left in place,
or where the JDBC-backed admin user has a weak / default password.

Maps to **CWE-798** (Hard-coded Credentials), **CWE-1392** (Use
of Default Credentials), **CWE-521** (Weak Password Requirements),
**CWE-1188** (Insecure Default Initialization), OWASP **A05:2021
Security Misconfiguration**, **A07:2021 Identification &
Authentication Failures**.

## Why this is a problem

Guacamole's JDBC auth backend (`guacamole-auth-jdbc-mysql` /
`-postgresql` / `-sqlserver`) seeds a single bootstrap admin via
`initdb.sql`:

```sql
INSERT INTO guacamole_user (entity_id, password_hash, password_salt, ...)
SELECT entity_id,
    x'CA458A7D494E3BE824F5E1E175A1556C0F8EEF2C2D7DF3633BEC4A29C4411960',
    x'FE24ADC5E11E2B25288D1704ABE67A79E342ECC26064CE69C5B3177795A82264',
    NOW()
FROM guacamole_entity WHERE name = 'guacadmin';
```

That hash is the SHA-256 of `"guacadmin"` + that exact salt — i.e.
the credentials are `guacadmin` / `guacadmin`. The bootstrap user
has `SYSTEM_ADMINISTER`, which means a network-reachable attacker
with the default password can:

- read every saved RDP / VNC / SSH connection (Guacamole stores
  the target-host passwords in the JDBC schema and decrypts them
  on demand),
- pivot into every host those connections target,
- create new admin users and lock the operator out,
- tail every active session via screen recording.

## Why LLMs ship this

The official Quick-Start docs and every "deploy guacamole in 5
minutes" tutorial run `initdb.sh` verbatim and tell the reader to
"log in as guacadmin / guacadmin and change the password". Models
reproduce the literals exactly when generating compose files,
properties files, or bootstrap SQL.

## Heuristic

In `guac*`-named files, `*.env*`, `docker-compose.*`, `*.y*ml`,
`*.sql`, `*.conf`, `*.properties`, `*.sh`, `Dockerfile*`,
`*.toml`, `*.json`, and any file whose body matches Guacamole
scope hints (`guacamole/guacamole`, `guacamole/guacd`,
`guacamole-auth-jdbc`, `/etc/guacamole`, `GUACAMOLE_HOME`,
`guacd_hostname`), we flag:

1. The literal upstream initdb hash
   `CA458A7D494E3BE824F5E1E175A1556C0F8EEF2C2D7DF3633BEC4A29C4411960`
   (case-insensitive).
2. Any line with `guacadmin` AND a plaintext-credential shape
   (`PASSWORD=guacadmin`, `pass: guacadmin`,
   `'guacadmin', 'guacadmin'` SQL row).
3. `mysql-username` / `guacamole-username` / `postgres-username`
   = `guacadmin` paired with a weak DB password (empty,
   `guacadmin`, `guacamole`, `password`, `changeme`, `secret`,
   `admin`, `root`, `12345*`, `qwerty`, `letmein`, or `< 12`
   chars).

We do NOT flag:

- `${...}` / `{{ ... }}` template references.
- Long high-entropy passwords not in the weak list.
- `.md` / `.rst` / `.txt` / `.adoc` prose.
- Files with no Guacamole scope hint.

## Usage

```sh
python3 detect.py path/to/file_or_dir [more...]
```

Exit codes: `0` clean, `1` findings, `2` usage error.

## Worked example

```sh
$ cd templates/llm-output-guacamole-default-guacadmin-credentials-detector
$ ./smoke.sh
bad=4/4 good=0/4
PASS
```

## Fixtures

`examples/bad/`:

- `01_guacamole_initdb.sql` — upstream `initdb.sql` with the
  literal `guacadmin` / `guacadmin` bootstrap hash.
- `02_docker-compose.yml` — compose file with
  `MYSQL_USER: guacadmin` / `MYSQL_PASSWORD: guacadmin`.
- `03_guacamole.properties` — `mysql-username: guacadmin` paired
  with `mysql-password: changeme`.
- `04_run_guacamole.sh` — `docker run` wrapper using upstream
  defaults.

`examples/good/`:

- `01_guacamole.properties` — credentials injected from
  `${GUACAMOLE_DB_USER}` / `${GUACAMOLE_DB_PASS}`.
- `02_docker-compose.yml` — same, plus loopback bind on `8080`.
- `03_guacamole_postrotate.sql` — bootstrap row replaced with a
  per-operator account, original `guacadmin` row deleted.
- `04_doc_only.md` — README in prose; `.md` is not scanned.

## Suggested remediation

```sh
# Right after initdb completes, rotate via the Guacamole CLI:
docker exec -it guacamole sh -c '
  guacctl create-user --username "ops-$(openssl rand -hex 3)" \
                       --password "$(openssl rand -base64 24)" \
                       --admin
  guacctl delete-user --username guacadmin
'
```

```yaml
services:
  guacamole:
    image: guacamole/guacamole:1.5.5
    ports:
      - "127.0.0.1:8080:8080"  # bind loopback; reverse-proxy w/ TLS
    environment:
      GUACD_HOSTNAME: guacd
      MYSQL_HOSTNAME: db
      MYSQL_DATABASE: guacamole_db
      MYSQL_USER: ${GUACAMOLE_DB_USER}
      MYSQL_PASSWORD: ${GUACAMOLE_DB_PASS}
```

Always front Guacamole with TLS — RDP/VNC/SSH credentials are
otherwise plumbed over plaintext HTTP.
