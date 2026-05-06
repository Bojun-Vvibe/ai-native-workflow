# llm-output-outline-secret-key-default-detector

Stdlib-only Python detector that flags **Outline** (the open-source
team wiki / knowledge base by [outline.com](https://www.getoutline.com),
*not* the Outline VPN client) deployments where `SECRET_KEY` or
`UTILS_SECRET` is left at the upstream `.env.sample` placeholder
(`generate_a_new_key`), an empty string, or an obvious weak literal.

Maps to **CWE-798** (Hard-coded Credentials), **CWE-1392** (Use of
Default Credentials), **CWE-330** (Insufficiently Random Values),
**CWE-1188** (Insecure Default Initialization), **CWE-384**
(downstream: Session Fixation, since the forged session cookie will
be accepted), OWASP **A02:2021 Cryptographic Failures**, **A05:2021
Security Misconfiguration**, **A07:2021 Identification &
Authentication Failures**.

## Why this is a problem

Outline uses two long-lived secrets:

- `SECRET_KEY` — signs / encrypts user session cookies and a handful
  of internal HMAC tokens.
- `UTILS_SECRET` — shared secret for internal `/api/utils.*`
  endpoints (notably `utils.gc` for the OCR / file pipeline).
  Outline trusts these endpoints as if they came from itself,
  bypassing the regular ACL layer.

Knowing `SECRET_KEY` lets an attacker forge a session cookie for
any user (including the workspace admin) and read or rewrite every
doc in the workspace. Knowing `UTILS_SECRET` lets them hit
internal-only endpoints that bypass ACL.

## Why LLMs ship this

The upstream `.env.sample` ships with the literal text:

```sh
# Generate a hex-encoded 32-byte random key. You should use
# `openssl rand -hex 32` in your terminal to generate a random
# value.
SECRET_KEY=generate_a_new_key
UTILS_SECRET=generate_a_new_key
```

Every "deploy outline in 5 minutes" tutorial copies this verbatim.
Models reproduce the placeholder exactly, or fall back to obvious
literals (`changeme`, `secret`, `outline`) when generating compose
files from scratch.

## Heuristic

In `outline*`-named files, `*.env*`, `docker-compose.*`, `*.y*ml`,
`*.conf`, `*.sh`, `Dockerfile*`, `*.toml`, `*.json`, and any file
whose body matches Outline scope hints (`outlinewiki/outline`,
`getoutline/outline`, `utils.gc`, `default_language=en_us`), we flag:

1. `SECRET_KEY=<weak>` / `SECRET_KEY: <weak>`
2. `UTILS_SECRET=<weak>` / `UTILS_SECRET: <weak>`

`<weak>` is one of:

- empty
- `generate_a_new_key` (upstream literal)
- `change_me`, `changeme`, `change-me`, `changeit`
- `secret`, `password`, `default`, `test`, `demo`, `example`
- `outline`, `key`, `secretkey`, `secret_key`, `utils_secret`
- `12345*`, `qwerty`, `letmein`, `admin`, `root`
- any value < 64 hex chars (Outline docs require `openssl rand
  -hex 32` = 64 hex chars).

We do NOT flag:

- `${...}` / `{{ ... }}` template references — assume the real
  value is injected from a secret store at runtime.
- Long high-entropy values (>= 64 chars).
- `.md` / `.rst` / `.txt` / `.adoc` prose.
- Files with no Outline scope hint — so a generic
  `SECRET_KEY=foo` in a Django `settings.py` is left alone (this
  is the most important false-positive guard for this detector).

## Usage

```sh
python3 detect.py path/to/file_or_dir [more...]
```

Exit codes: `0` clean, `1` findings, `2` usage error.

## Worked example

```sh
$ cd templates/llm-output-outline-secret-key-default-detector
$ ./smoke.sh
bad=4/4 good=0/4
PASS
```

## Fixtures

`examples/bad/`:

- `01_outline.env.sample` — upstream sample with both keys at
  `generate_a_new_key`.
- `02_docker-compose.yml` — compose file with `SECRET_KEY:
  changeme` and `UTILS_SECRET: changeme`.
- `03_run_outline.sh` — shell wrapper exporting `SECRET_KEY=secret`
  and `UTILS_SECRET=outline`.
- `04_k8s_outline.yaml` — k8s ConfigMap with both keys at
  `generate_a_new_key`.

`examples/good/`:

- `01_outline.env.sample` — long high-entropy hex secrets.
- `02_docker-compose.yml` — `${OUTLINE_SECRET_KEY}` /
  `${OUTLINE_UTILS_SECRET}` injected.
- `03_k8s_secret.yaml` — k8s `Secret` populated by external-secrets
  via Helm template refs.
- `04_doc_only.md` — README mentioning the placeholder string in
  prose; `.md` is not scanned.

## Suggested remediation

```sh
openssl rand -hex 32 | sudo tee /etc/outline/secret_key
openssl rand -hex 32 | sudo tee /etc/outline/utils_secret
chmod 600 /etc/outline/*
```

```yaml
services:
  outline:
    image: outlinewiki/outline:0.78.0
    ports:
      - "127.0.0.1:3000:3000"
    environment:
      SECRET_KEY: ${OUTLINE_SECRET_KEY}
      UTILS_SECRET: ${OUTLINE_UTILS_SECRET}
      URL: https://wiki.example.com
```

Front Outline behind a reverse proxy with TLS; never expose
port 3000 publicly. Rotate `SECRET_KEY` periodically — note this
will invalidate every active session, which is intentional.
`UTILS_SECRET` should be rotated whenever you touch the OCR / file
pipeline.
