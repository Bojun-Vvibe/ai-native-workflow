# llm-output-sentry-system-secret-key-default-detector

Flags self-hosted Sentry deployments whose `system.secret-key`
is left at the upstream-template placeholder (most commonly the
literal `!!changeme!!` sentinel emitted by `install.sh` in
`getsentry/self-hosted`, or other documented placeholders such
as `changeme`, `please-change-me`, `<your-secret-key>`, etc.).

## Upstream

- `getsentry/self-hosted` — https://github.com/getsentry/self-hosted
- `getsentry/sentry` — https://github.com/getsentry/sentry
- Self-hosted secret-key doc:
  https://develop.sentry.dev/self-hosted/#sentry-secret-key
- Tested heuristics against self-hosted versions 23.x .. 24.x
  where `install.sh` still emits the `!!changeme!!` sentinel
  into `sentry/sentry.conf.py` and `sentry/config.yml`.

## What it detects

All gated by an in-file Sentry context token (any of:
`sentry`, `getsentry`, `snuba`, `SENTRY_*`, `sentry.conf.py`):

1. `system.secret-key: '!!changeme!!'` (or any of the placeholder
   strings) in a YAML/`config.yml` style line.
2. `SECRET_KEY = '!!changeme!!'` Python assignment in a Sentry
   settings module.
3. `SENTRY_SECRET_KEY=!!changeme!!` env var or
   `docker-compose` env entry.

## Why this is dangerous

Sentry's `system.secret-key` is the cryptographic root of the
self-hosted install. It signs and validates:

- session cookies (Django `SECRET_KEY` semantics) → session
  forgery / privilege escalation to a Sentry superuser;
- HMAC tokens used for "magic link" email auth and password
  reset → attacker-issued reset tokens;
- relay-to-sentry signed requests when an external Relay is
  configured → arbitrary event ingestion / spoofing of any
  project's events;
- the CSRF token derivation → bypass of CSRF on the
  `/api/0/` admin surface.

Anyone who knows the value can mint a valid superuser session
without ever touching the database. The `!!changeme!!` literal
is shipped in the upstream template and is therefore world-known.

## CWE / OWASP refs

- **CWE-798**: Use of Hard-coded Credentials
- **CWE-1392**: Use of Default Credentials
- **CWE-321**: Use of Hard-coded Cryptographic Key
- **CWE-1188**: Insecure Default Initialization of Resource
- **OWASP A02:2021** — Cryptographic Failures
- **OWASP A07:2021** — Identification and Authentication Failures

## False positives

Skipped:

- Files with no Sentry context (an unrelated Django
  `SECRET_KEY = 'changeme'` for a different app).
- Comment-only mentions of the default in docs.
- A real, high-entropy key emitted by
  `sentry config generate-secret-key` (does not match any
  placeholder string).

## Run

```
python3 detect.py path/to/file-or-dir [more...]
```

Exit codes: `0` clean, `1` findings, `2` usage error.

## Worked example

```
$ ./smoke.sh
bad=4/4 good=0/3
PASS
```

Four `examples/bad/` files (a `config.yml` with
`system.secret-key: '!!changeme!!'`, a `sentry.conf.py` with
`SECRET_KEY = 'changeme'`, a `docker-compose.yml` with
`SENTRY_SECRET_KEY: '!!changeme!!'`, and an `.env` with
`SENTRY_SECRET_KEY=please-change-me`) each trip the detector.
Three `examples/good/` files (a `config.yml` whose
`system.secret-key` holds a real 64-char hex string, a
`sentry.conf.py` that reads the key from `os.environ`, and a
`docker-compose.yml` that pulls `SENTRY_SECRET_KEY` from a
secret reference) all stay clean.
