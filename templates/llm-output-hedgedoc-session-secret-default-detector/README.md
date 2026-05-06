# llm-output-hedgedoc-session-secret-default-detector

Stdlib-only **bash** detector that flags HedgeDoc (formerly CodiMD)
deployments where the session-signing secret
(`CMD_SESSION_SECRET` env var or `sessionSecret` in `config.json`)
is left at the upstream literal `secret`, an empty value, an
obvious placeholder (`changeme`, `PleaseChangeMe`, etc.), or a
sub-16-character low-entropy value.

Maps to **CWE-798** (Hard-coded Credentials), **CWE-1392** (Use of
Default Credentials), **CWE-330** (Insufficiently Random Values),
**CWE-1188** (Insecure Default Initialization), OWASP
**A02:2021 Cryptographic Failures**, **A05:2021 Security
Misconfiguration**, **A07:2021 Identification & Authentication
Failures**.

## Why this is a problem

HedgeDoc is a self-hosted collaborative markdown editor. The
session secret is the HMAC key behind the `connect.sid` cookie
that authenticates every logged-in user. The upstream
`config.json.example` ships the literal value `"secret"`, and the
docker README's environment block shows `CMD_SESSION_SECRET=secret`
as a "fill this in later" placeholder.

If an attacker knows the session secret, they can mint a valid
`connect.sid` cookie for any user ID **offline** — no password,
no OAuth dance, no DB access. Paste the cookie into a browser and
you are that user, with full read/write access to every note that
user can see, plus the ability to invite collaborators and create
API tokens.

This is independent of the auth backend (LDAP, OAuth, local) —
the session cookie is signed the same way regardless of how the
user originally logged in.

## Why LLMs ship this

The upstream `docker-compose.yml`, `config.json.example`, and
nearly every "deploy HedgeDoc with docker-compose" tutorial show
`CMD_SESSION_SECRET=secret` or `"sessionSecret": "secret"`
verbatim. Models faithfully reproduce these literals, or invent
adjacent placeholders like `hedgedoc`, `codimd`, `changeme`,
`PleaseChangeMe`, `your-secret-here`.

## What this detector does

Scans a single file or recursively scans a directory for the
following file patterns:

- `*.env`, `.env`
- `docker-compose*.yml`, `docker-compose*.yaml`
- `Dockerfile`
- `config.json`, `config.json.example`
- `*.conf`

For each matched file it inspects:

- `CMD_SESSION_SECRET=...` (env-style)
- `"sessionSecret": ...` and `sessionSecret: ...` (config.json /
  YAML style)

and FAILS the file if the value is:

1. empty,
2. shorter than 16 characters,
3. one of the known upstream/example placeholders (`secret`,
   `hedgedoc`, `codimd`, `changeme`, `change-me`, `change_me`,
   `changethis`, `change-this`, `default`, `session-secret`,
   `sessionsecret`, `your-secret-here`, `replace-me`, `replaceme`,
   `PleaseChangeMe`).

Comment lines (`#`, `//`) are ignored, so docs that mention the
placeholder in a `# DO NOT use` comment do not trip the detector.

## Usage

```
./detect.sh <config-file-or-dir>
```

## Exit codes

| Code | Meaning                                                    |
|------|------------------------------------------------------------|
| 0    | PASS — no defaulted/weak session secret observed           |
| 1    | FAIL — at least one defaulted/weak session secret observed |
| 2    | usage error (missing arg or path does not exist)           |

## Validation

Result on the bundled fixtures: **bad=4/4 detected, good=0/4 false
positives, PASS**. Full command output is recorded in `RUN.md`.

## Limitations

- Does not parse JSON; the `sessionSecret` matcher is line-based
  and therefore expects the typical
  `"sessionSecret": "<value>",` layout.
- Does not estimate entropy beyond a length check; a 16+ char
  string of all `a`s will pass. Pair with a generic entropy
  linter for stricter coverage.
- Does not rotate / detect already-leaked-but-changed secrets;
  pair with a separate secret-leak scan over git history.
