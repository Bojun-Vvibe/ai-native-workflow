# llm-output-wallabag-secret-default-detector

Stdlib-only **bash** detector that flags Wallabag deployments where
`SYMFONY__ENV__SECRET` (the Symfony application secret used to sign
CSRF tokens, "remember me" cookies, and password-reset URL hashes)
is left at the upstream placeholder, an empty string, or an
obviously low-entropy string.

Maps to **CWE-798** (Hard-coded Credentials), **CWE-1392** (Use of
Default Credentials), **CWE-330** (Insufficiently Random Values),
**CWE-1188** (Insecure Default Initialization), OWASP
**A02:2021 Cryptographic Failures**, **A05:2021 Security
Misconfiguration**.

## Why this is a problem

Wallabag is a self-hosted read-it-later service. The Symfony
`secret` parameter (exposed as `SYMFONY__ENV__SECRET` in the
official docker image) is used by the framework to:

- sign CSRF tokens on every form,
- HMAC the `REMEMBERME` cookie that re-authenticates users for up
  to a year,
- derive the password-reset URL token,
- sign the optional 2FA recovery payloads.

If an attacker knows `secret`, they can mint a `REMEMBERME` cookie
for any user ID **offline** — no password, no DB access, no
network round-trip to the Wallabag host. They can also forge
password-reset links and CSRF tokens to drive any privileged
form against an authenticated victim's session.

## Why LLMs ship this

The upstream `docker-compose.yml`, the install docs, and most
"deploy Wallabag in 5 minutes" guides ship the literal value
`ThisTokenIsNotSoSecretChangeIt`. Models faithfully reproduce
this, or invent close cousins like `changeme`, `secret`,
`replace-me`, `default`.

## What this detector does

Scans a single file or recursively scans a directory for the
following file patterns:

- `*.env`, `.env`
- `parameters*.yml`, `parameters*.yaml`
- `docker-compose*.yml`, `docker-compose*.yaml`
- `Dockerfile`
- `*.conf`

For each matched file it inspects assignments of the form:

- `SYMFONY__ENV__SECRET=...` (env-style)
- `secret: ...` (parameters.yml style)

and FAILS the file if the value is:

1. empty,
2. shorter than 16 characters,
3. one of a small list of known upstream/example placeholders
   (`ThisTokenIsNotSoSecretChangeIt`, `changeme`, `changethis`,
   `default`, `secret`, `password`, `your-secret-here`,
   `replace-me`, `RandomToken`, `MySecretToken`, `ChangeThisToken`).

Comment lines (`# ...`) are ignored.

## Usage

```
./detect.sh <config-file-or-dir>
```

## Exit codes

| Code | Meaning                                                    |
|------|------------------------------------------------------------|
| 0    | PASS — no defaulted/weak SECRET observed                   |
| 1    | FAIL — at least one defaulted/weak SECRET observed         |
| 2    | usage error (missing arg or path does not exist)           |

## Validation

Run against the bundled fixtures:

```
$ for f in fixtures/bad/*;  do ./detect.sh "$f" >/dev/null || echo "BAD detected: $f"; done
$ for f in fixtures/good/*; do ./detect.sh "$f" >/dev/null && echo "GOOD passed:  $f"; done
```

Result on the bundled fixtures: **bad=4/4 detected, good=0/4 false
positives, PASS**. Full command output is recorded in `RUN.md`.

## Limitations

- Does not parse YAML; the `parameters.yml` matcher is line-based
  and therefore expects the typical 4-space-indented `secret: VAL`
  layout that ships with Wallabag's `app/config/parameters.yml.dist`.
- Does not estimate entropy beyond a length check; a 16+ char
  string of all `a`s will pass. Pair with a generic entropy linter
  for stricter coverage.
- Does not follow `env_file:` references inside compose files —
  point the detector at the referenced file directly, or pass the
  parent directory.
