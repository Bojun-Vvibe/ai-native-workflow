# llm-output-umami-app-secret-default-detector

Stdlib-only Python detector that flags **Umami** (privacy-focused
web analytics) deployments where `APP_SECRET` (the JWT signing key
for admin sessions and API tokens) is left at an empty string, an
obvious placeholder, or a short low-entropy value.

Maps to **CWE-798** (Hard-coded Credentials), **CWE-1392** (Use of
Default Credentials), **CWE-330** (Insufficiently Random Values),
**CWE-521** (Weak Password Requirements), **CWE-1188** (Insecure
Default Initialization), OWASP **A02:2021 Cryptographic Failures**,
**A05:2021 Security Misconfiguration**, **A07:2021 Identification &
Authentication Failures**.

## Why this is a problem

Umami uses `APP_SECRET` to sign:

- the admin login JWT cookie
- API tokens minted via `/api/auth/login` and the share-link API
- password-reset tokens

If you know `APP_SECRET`, you can forge an admin JWT for any user
ID **offline** — no password, no database, no network access to
the Umami host needed. Mint a cookie locally, paste it into a
browser, and you are root in the analytics tenant: every site's
pageview data is exposed, every user's password can be reset, and
you can pivot to whatever upstream the dashboard is embedded in.

`HASH_SALT` (older umami releases) has the same property for
session-token derivation.

## Why LLMs ship this

The upstream `docker-compose.yml`, the README, and almost every
"deploy umami in 5 minutes" blog post show `APP_SECRET=replace-me`
or `APP_SECRET=` (empty), with a TODO comment. Models reproduce
the placeholder verbatim, or invent close variants like
`your-secret-here`, `changeme`, `umami`.

## Heuristic

In `docker-compose.*`, `*.yml`, `*.yaml`, `*.env.example`, `*.ini`,
`*.conf`, `*.sh`, `Dockerfile*`, `*.toml`, `*.json`, and any file
whose basename contains `umami`, we flag:

1. `APP_SECRET` empty.
2. `APP_SECRET` set to a known placeholder (`umami`, `secret`,
   `secretkey`, `changeme`, `replace-me`, `your-secret-here`,
   `default`, `password`, `admin`, `12345*`, …).
3. `APP_SECRET` shorter than 32 characters.
4. `HASH_SALT` (legacy) — same checks.

We do NOT flag:

- `${...}` / `{{ ... }}` template references.
- Long high-entropy values (>= 32 chars).
- Markdown / RST / TXT prose mentions.
- Files with no umami scope hint.

## Usage

```sh
python3 detect.py path/to/file_or_dir [more...]
```

Exit codes: `0` clean, `1` findings, `2` usage error.

## Worked example

```sh
$ cd templates/llm-output-umami-app-secret-default-detector
$ ./smoke.sh
bad=4/4 good=0/4
PASS
```

## Fixtures

`examples/bad/`:

- `01_docker-compose.yml` — quickstart with `APP_SECRET=replace-me`.
- `02_umami.env.example` — empty `APP_SECRET`, weak `HASH_SALT`.
- `03_run_umami.sh` — shell wrapper exporting `APP_SECRET=umami`.
- `04_k8s_umami.yaml` — k8s ConfigMap with
  `APP_SECRET=your-secret-here`.

`examples/good/`:

- `01_docker-compose.yml` — secrets injected via `${...}`.
- `02_umami.env.example` — strong random secrets.
- `03_doc_only.md` — README mentioning placeholders in prose; not
  a config file.
- `04_k8s_secret.yaml` — k8s `Secret` with strong random values.

## Suggested remediation

```sh
# generate once, store in your secret manager
APP_SECRET="$(openssl rand -base64 48)"
HASH_SALT="$(openssl rand -base64 48)"
```

```yaml
services:
  umami:
    image: ghcr.io/umami-software/umami:postgresql-latest
    ports:
      - "127.0.0.1:3000:3000"   # do NOT expose admin to the public
    environment:
      DATABASE_URL: ${DATABASE_URL}
      APP_SECRET: ${UMAMI_APP_SECRET}
      HASH_SALT: ${UMAMI_HASH_SALT}
```

Rotate `APP_SECRET` whenever an admin leaves the team — every
existing JWT will be invalidated, forcing a re-login on the next
request.
