# llm-output-miniflux-create-admin-default-credentials-detector

Stdlib-only Python detector that flags **Miniflux** (the
minimalist self-hosted RSS reader, [miniflux.app](https://miniflux.app))
deployments where the `CREATE_ADMIN=1` bootstrap flow is left at
default / weak credentials, or where `CREATE_ADMIN=1` is set with
no `ADMIN_PASSWORD` defined alongside it.

Maps to **CWE-798** (Hard-coded Credentials), **CWE-1392** (Use
of Default Credentials), **CWE-521** (Weak Password Requirements),
**CWE-1188** (Insecure Default Initialization), OWASP **A05:2021
Security Misconfiguration**, **A07:2021 Identification &
Authentication Failures**.

## Why this is a problem

Miniflux supports a one-shot first-boot admin bootstrap controlled
by three env vars:

```
CREATE_ADMIN=1
ADMIN_USERNAME=admin
ADMIN_PASSWORD=test123
```

The literal `test123` comes straight from the upstream
`docker-compose.yml` example in the README. Anyone who reaches
the Miniflux HTTP port with these credentials can:

- read every subscribed feed and saved article (which often
  contains private OAuth-callback URLs, recovery emails the user
  starred, internal feeds from Sentry / GitHub / Jira /
  Confluence, etc.),
- abuse the integrated fetcher to make outbound HTTP requests on
  the operator's behalf — Miniflux follows redirects and will
  happily fetch from `http://169.254.169.254/...` (cloud
  metadata SSRF) unless `FETCHER_PROXY` / a deny-list is set,
- mint API tokens that survive password changes,
- create new admin users.

## Why LLMs ship this

The literal `admin`/`test123` pair appears in the upstream README
as the worked example; almost every blog post and tutorial copies
it verbatim. Models reproduce both literals when asked for "a
docker-compose for miniflux" or "deploy miniflux".

## Heuristic

In `miniflux*`-named files, `*.env*`, `docker-compose.*`,
`*.y*ml`, `*.conf`, `*.sh`, `Dockerfile*`, `*.toml`, `*.json`,
and any file whose body matches Miniflux scope hints
(`miniflux/miniflux`, `MINIFLUX_*`, `image: miniflux`,
`/var/lib/miniflux`, `run_migrations`, `polling_frequency`,
`fetcher_proxy`, `database_url=postgres`), we flag:

1. `ADMIN_USERNAME = <weak>` — empty, `admin`, `root`,
   `miniflux`, `user`, `default`, `test`, `demo`, `guest`.
2. `ADMIN_PASSWORD = <weak>` — empty, `test123` (upstream
   literal), `admin`, `password`, `miniflux`, `changeme`,
   `secret`, `12345*`, `qwerty`, `letmein`, `root`, `default`,
   `test`, `demo`, `p@ssw0rd`, `password1`, or any value
   `< 12` chars.
3. `CREATE_ADMIN=1` AND no `ADMIN_PASSWORD` defined in the same
   file — bootstrap will fall back to whatever literal is baked
   into the container or wrapper script; the password is
   effectively undefined and almost certainly weak in practice.

We do NOT flag:

- `${...}` / `{{ ... }}` template references.
- Long high-entropy passwords not in the weak list.
- `.md` / `.rst` / `.txt` / `.adoc` prose.
- Files with no Miniflux scope hint.

## Usage

```sh
python3 detect.py path/to/file_or_dir [more...]
```

Exit codes: `0` clean, `1` findings, `2` usage error.

## Worked example

```sh
$ cd templates/llm-output-miniflux-create-admin-default-credentials-detector
$ ./smoke.sh
bad=4/4 good=0/4
PASS
```

## Fixtures

`examples/bad/`:

- `01_miniflux.env.example` — upstream README example with
  `ADMIN_USERNAME=admin`, `ADMIN_PASSWORD=test123`.
- `02_docker-compose.yml` — `admin` / `changeme`.
- `03_run_miniflux.sh` — `docker run` wrapper with
  `miniflux` / `miniflux`.
- `04_miniflux.conf` — `CREATE_ADMIN=1` set with no
  `ADMIN_PASSWORD` anywhere in the file.

`examples/good/`:

- `01_miniflux.env.example` — non-default user, 32-char random
  password, loopback `LISTEN_ADDR`.
- `02_docker-compose.yml` — both injected from
  `${MINIFLUX_BOOTSTRAP_USER}` / `${MINIFLUX_BOOTSTRAP_PASS}`.
- `03_miniflux.conf` — `CREATE_ADMIN` intentionally absent;
  operator runs `miniflux -create-admin` once interactively.
- `04_doc_only.md` — README in prose; `.md` is not scanned.

## Suggested remediation

```sh
# Generate strong bootstrap credentials and inject via env at boot.
export MINIFLUX_BOOTSTRAP_USER="ops-$(openssl rand -hex 3)"
export MINIFLUX_BOOTSTRAP_PASS="$(openssl rand -base64 24)"
docker compose up -d miniflux
# Or run interactively, once:
docker exec -it miniflux miniflux -create-admin
```

```yaml
services:
  miniflux:
    image: miniflux/miniflux:2.1.4
    ports:
      - "127.0.0.1:8080:8080"   # bind loopback; reverse-proxy w/ TLS
    environment:
      DATABASE_URL: postgres://miniflux:${MINIFLUX_DB_PASS}@db/miniflux?sslmode=require
      RUN_MIGRATIONS: "1"
      CREATE_ADMIN: "1"
      ADMIN_USERNAME: ${MINIFLUX_BOOTSTRAP_USER}
      ADMIN_PASSWORD: ${MINIFLUX_BOOTSTRAP_PASS}
```

Also set `FETCHER_PROXY` or a deny-list to block the integrated
fetcher from reaching cloud-metadata IPs (`169.254.169.254`,
`fd00:ec2::254`, link-local) and internal RFC1918 ranges; this
closes the SSRF path even if the admin password is later
compromised.
