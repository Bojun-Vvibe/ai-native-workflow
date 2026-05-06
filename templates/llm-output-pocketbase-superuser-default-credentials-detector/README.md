# llm-output-pocketbase-superuser-default-credentials-detector

Stdlib-only **bash** detector that flags PocketBase deployments
where the initial superuser/admin account is bootstrapped with a
literal placeholder email/password pair such as
`admin@example.com` / `1234567890`, `test@test.com` / `password`,
or `admin@admin.com` / `changeme`.

Maps to **CWE-798** (Hard-coded Credentials), **CWE-1392** (Use of
Default Credentials), **CWE-521** (Weak Password Requirements),
OWASP **A07:2021 Identification and Authentication Failures**,
**A05:2021 Security Misconfiguration**.

## Why this is a problem

PocketBase ships a single embedded SQLite-backed admin UI that
exposes every collection, every record, every file blob, and the
real-time event stream. Whoever holds the superuser credential
owns the entire backend and can mint API tokens for any user.

The CLI subcommands `pocketbase superuser create|upsert` (and the
older `pocketbase admin create|upsert`) take the email and
password as plain positional arguments. Sample blog posts and
"deploy PocketBase in 2 minutes" recipes routinely use
`admin@example.com 1234567890` because it satisfies PocketBase's
10-character minimum and is short enough to type in a demo.

If the deployment ships with that literal pair, the system is
fully compromised the moment its URL is reachable: drive-by
admin-panel scanners try `admin@example.com:1234567890` first.

## Why LLMs ship this

The most-cited PocketBase tutorials, the canned `Dockerfile`s on
GitHub, and the official quickstart all use the same handful of
placeholder pairs. Models trained on that corpus reproduce them
faithfully when asked to "write a Dockerfile that bootstraps a
PocketBase admin", or "show me a Go `OnBootstrap` hook that
creates the initial admin".

## What this detector does

Scans a single file or recursively scans a directory for the
following file patterns:

- `*.sh`, `*.bash`
- `Dockerfile`
- `docker-compose*.yml`, `docker-compose*.yaml`
- `*.service` (systemd units)
- `*.go` (programmatic bootstrap)
- `*.md`, `*.markdown` (install guides)
- `entrypoint*`, `bootstrap*`, `init*`

For each matched file it inspects:

1. CLI invocations of the form
   `pocketbase superuser create|upsert <email> <password>` and
   `pocketbase admin create|upsert <email> <password>`,
2. Programmatic Go bootstrap lines of the form
   `admin.SetPassword("<literal>")`.

A finding is emitted when the email is in the known-placeholder
list (`admin@example.com`, `admin@admin.com`, `test@test.com`,
`root@localhost`, …) **or** the password is shorter than the
PocketBase 10-char minimum or appears in the known-weak list
(`1234567890`, `password`, `password123`, `changeme`, `admin`,
`pocketbase`, …).

Comment lines (`# ...`) are ignored. Bootstraps that pull email
and password from environment variables (e.g. `"$PB_ADMIN_EMAIL"
"$PB_ADMIN_PASSWORD"`) pass cleanly because the detector treats
shell-variable tokens as opaque rather than literal credentials.

## Usage

```
./detect.sh <file-or-dir>
```

## Exit codes

| Code | Meaning                                                |
|------|--------------------------------------------------------|
| 0    | PASS — no defaulted superuser bootstrap observed       |
| 1    | FAIL — at least one defaulted superuser bootstrap      |
| 2    | usage error (missing arg or path does not exist)       |

## Validation

```
$ for f in fixtures/bad/*;  do ./detect.sh "$f" >/dev/null || echo "BAD detected: $f"; done
$ for f in fixtures/good/*; do ./detect.sh "$f" >/dev/null && echo "GOOD passed:  $f"; done
```

Result on the bundled fixtures: **bad=4/4 detected, good=0/4 false
positives, PASS**. Full command output is recorded in `RUN.md`.

## Limitations

- Single-line matcher. A multi-line Go bootstrap that splits
  `admin.SetPassword(` across lines will not match — keep the
  literal on one line, or pair this detector with a stricter
  AST-based Go linter.
- No correlation between adjacent `Email = "..."` and
  `SetPassword("...")` lines; weak password alone is enough to
  fire on `.go` files.
- Does not parse YAML; the compose-file matcher is line-based
  and relies on the typical `command: >` / `command: sh -c "..."`
  layout that the upstream community publishes.
- Does not catch credentials passed via a build arg such as
  `ARG ADMIN_PASSWORD=password123` followed by
  `RUN pocketbase superuser create $ADMIN_EMAIL $ADMIN_PASSWORD`;
  pair with a generic build-arg-default linter for that case.
