# llm-output-authelia-default-jwt-secret-detector

Stdlib-only Python detector that flags **Authelia** configurations
shipping the well-known placeholder JWT / session / storage-encryption
secrets copied verbatim from the upstream example config and
`compose/lite/` tutorial.

Maps to **CWE-798** (use of hard-coded credentials), **CWE-321**
(use of hard-coded cryptographic key), and **CWE-1188** (insecure
default initialization of resource).

## Why this matters

Authelia (`authelia/authelia`, v4.x including v4.38+) signs SSO
identity tokens with `jwt_secret` (or
`identity_validation.reset_password.jwt_secret` on newer releases),
encrypts session cookies with `session.secret`, and encrypts the
storage backend at rest with `storage.encryption_key`.

The upstream repository ships an example config
(`internal/configuration/test_resources/config.yml`,
`compose/lite/authelia/configuration.yml`, plus various docs pages)
that uses placeholder values such as:

- `a_very_important_secret`
- `unsecure_session_secret`
- `a_very_important_session_secret`
- `a_very_important_storage_encryption_key`
- `you_must_generate_a_random_string_of_more_than_eighty_characters_to_use_here`

LLMs almost always copy these straight into the user's config / .env
/ compose file. Anything signed with one of those secrets is
forge-able by anyone who has read the public Authelia repo -- a
complete authentication bypass for the SSO portal.

Upstream reference (v4.x):

- <https://github.com/authelia/authelia>
- `compose/lite/authelia/configuration.yml` (placeholder values)
- `internal/configuration/validator/*` (length checks, >=32 bytes)
- Docs: <https://www.authelia.com/configuration/identity-validation/reset-password/>

## Heuristic

We flag any of the following, outside `#` / `//` comments:

1. A YAML key `jwt_secret`, `encryption_key`, or `secret:` nested
   under `session:` / `storage:` / `notifier:`, whose value is one
   of the upstream placeholder strings (case-insensitive).
2. The same in env-var form: `AUTHELIA_JWT_SECRET=...`,
   `AUTHELIA_SESSION_SECRET=...`,
   `AUTHELIA_STORAGE_ENCRYPTION_KEY=...`.
3. Any of those keys whose value is empty or shorter than 32 bytes
   (Authelia v4.38+ rejects this at startup, but earlier versions
   silently accepted it and LLMs still emit it).

Each occurrence emits one finding line.

## What we accept (no false positive)

- 64-hex-char secrets generated with `openssl rand -hex 32`.
- `_FILE` variants (`AUTHELIA_JWT_SECRET_FILE: /run/secrets/...`)
  pulled from a mounted secrets store -- nothing dangerous on disk
  in the repo.
- Runbook / docs files that mention the bad placeholders only as
  warnings.

## What we flag

- `compose/lite/authelia/configuration.yml`-style configs copied
  unchanged.
- `.env` files with `AUTHELIA_JWT_SECRET=changeme`.
- Compose `environment:` blocks setting placeholders directly.
- Configs with very short secrets like `secret: short`.

## Limits / known false negatives

- We do not parse fully-quoted multi-line YAML scalars.
- We do not validate entropy beyond length; a 32-char string of
  `xxxxxxxx...` will pass the length check. Pair this detector with
  a generic low-entropy scanner if that matters.
- We do not detect Authelia-templated Helm values resolved at
  install time.

## Usage

```bash
python3 detect.py path/to/repo/
python3 detect.py configuration.yml docker-compose.yml .env
```

Exit codes: `0` = no findings, `1` = findings (printed to stdout),
`2` = usage error.

## Smoke test

```
$ bash smoke.sh
bad=4/4 good=0/3
PASS
```

Layout:

```
examples/bad/
  01_lite_tutorial.yml         # placeholders from compose/lite tutorial
  02_env_placeholders.env.example  # .env with changeme / supersecret
  03_short_secrets.yml         # <32-byte secrets
  04_compose.yaml              # compose env vars set to placeholders
examples/good/
  01_strong_secrets.yml        # 64-hex-char secrets
  02_runbook.yml               # only mentions placeholders in comments
  03_compose_file_secrets.yaml # uses _FILE / docker secrets pattern
```
