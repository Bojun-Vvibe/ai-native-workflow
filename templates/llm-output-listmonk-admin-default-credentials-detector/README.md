# llm-output-listmonk-admin-default-credentials-detector

Stdlib-only Python detector that flags **listmonk** (newsletter /
mailing-list manager) deployments where the bootstrap superadmin is
left at the well-known quickstart values from the official
docker-compose.

Maps to **CWE-798** (Hard-coded Credentials), **CWE-1392** (Use of
Default Credentials), **CWE-521** (Weak Password Requirements),
**CWE-1188** (Insecure Default Initialization), OWASP **A05:2021
Security Misconfiguration**, **A07:2021 Identification &
Authentication Failures**.

## Why this is a problem

listmonk reads two env vars at first boot to seed the superadmin
account:

- `LISTMONK_ADMIN_USER`
- `LISTMONK_ADMIN_PASSWORD`

The official `docker-compose.yml` ships with both set to the
literal string `listmonk`. Anyone who can hit `/admin/` with those
credentials can:

- mint API tokens (full read/write to subscribers, lists, campaigns)
- import arbitrary subscriber CSVs
- send mail through the configured upstream SMTP relay — which
  almost always belongs to a real, warmed-up sender domain

The third bullet is the real damage: a default-credentialed
listmonk attached to an authenticated SES / Mailgun / Postmark
relay is an instant high-reputation open relay.

## Why LLMs ship this

Every "deploy listmonk in 5 minutes" tutorial copies the upstream
`docker-compose.yml` verbatim. Models reproduce the
`LISTMONK_ADMIN_USER=listmonk` / `LISTMONK_ADMIN_PASSWORD=listmonk`
pair exactly. They also fall back to obvious placeholders
(`admin`/`admin`, `admin`/`changeme`) when generating compose files
from scratch.

## Heuristic

In `docker-compose.*`, `*.yml`, `*.yaml`, `*.env.example`, `*.ini`,
`*.conf`, `*.sh`, `Dockerfile*`, `*.toml`, `*.json`, and any file
whose basename contains `listmonk`, we flag:

1. `LISTMONK_ADMIN_USER` set to: `listmonk`, `admin`, `root`,
   `user`, `test`, `demo`, or empty.
2. `LISTMONK_ADMIN_PASSWORD` set to: `listmonk`, `admin`, `root`,
   `password`, `passwd`, `pass`, `changeme`, `change-me`,
   `changeit`, `default`, `test`, `demo`, `12345*`, `qwerty`,
   `letmein`, `guest`, or empty.
3. `LISTMONK_ADMIN_PASSWORD` shorter than 12 characters.

We do NOT flag:

- `${...}` / `{{ ... }}` template references — assume the real value
  is injected from a secret store at runtime.
- Long high-entropy values (>= 12 chars).
- Doc / README mentions in prose (file is `.md` and ext is not
  scanned).
- Files with no listmonk scope hint.

## Usage

```sh
python3 detect.py path/to/file_or_dir [more...]
```

Exit codes: `0` clean, `1` findings, `2` usage error.

## Worked example

```sh
$ cd templates/llm-output-listmonk-admin-default-credentials-detector
$ ./smoke.sh
bad=4/4 good=0/4
PASS
```

## Fixtures

`examples/bad/`:

- `01_docker-compose.yml` — upstream quickstart with
  `listmonk`/`listmonk`.
- `02_listmonk.env.example` — env file with `admin`/`admin`.
- `03_run_listmonk.sh` — shell wrapper exporting
  `admin`/`changeme`.
- `04_k8s_listmonk.yaml` — k8s ConfigMap with `listmonk`/`listmonk`.

`examples/good/`:

- `01_docker-compose.yml` — secrets injected via `${...}`.
- `02_listmonk.env.example` — strong unique credentials.
- `03_doc_only.md` — README mentioning the quickstart string in
  prose; not a config file.
- `04_k8s_secret.yaml` — k8s `Secret` with strong random values.

## Suggested remediation

```sh
# generate once, store in your secret manager
LISTMONK_ADMIN_USER="ops-broadcast-$(openssl rand -hex 4)"
LISTMONK_ADMIN_PASSWORD="$(openssl rand -base64 24)"
```

```yaml
services:
  listmonk:
    image: listmonk/listmonk:v3.0.0
    ports:
      - "127.0.0.1:9000:9000"   # do NOT expose admin to the public
    environment:
      LISTMONK_ADMIN_USER: ${LISTMONK_ADMIN_USER}
      LISTMONK_ADMIN_PASSWORD: ${LISTMONK_ADMIN_PASSWORD}
```

Front the admin port with mTLS or an IP allow-list. Rotate the
bootstrap password on a schedule, and revoke it once a real SSO
admin account exists.
