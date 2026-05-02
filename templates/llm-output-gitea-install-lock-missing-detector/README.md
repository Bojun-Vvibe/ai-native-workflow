# llm-output-gitea-install-lock-missing-detector

Detect Gitea (self-hosted git server) `app.ini` configurations where
`INSTALL_LOCK` is missing, set to a falsy value, or only present as a comment
inside the `[security]` section. When `INSTALL_LOCK` is not `true`, Gitea
exposes the `/install` web wizard to anyone who can reach the server. The
first visitor can:

- Configure the database connection,
- Create the initial administrator account, and
- Achieve arbitrary code execution via the SQLite path field
  (a long-known, mass-exploited misconfiguration).

LLMs frequently emit `app.ini` snippets that omit `INSTALL_LOCK` entirely
when asked to "set up Gitea", because many tutorials assume the operator
will fill it in after the first-run wizard.

## What bad LLM output looks like

Missing entirely:

```ini
[security]
SECRET_KEY = changeme
INTERNAL_TOKEN = abc
```

Set to false:

```ini
[security]
INSTALL_LOCK = false
```

Only a comment, no real assignment:

```ini
[security]
; INSTALL_LOCK = true
```

Falsy values (`0`, `no`, `off`, `false`) are all treated as bad.

## What good LLM output looks like

```ini
[security]
INSTALL_LOCK = true
SECRET_KEY = a_real_random_value
```

`true`, `1`, `yes`, `on` (case-insensitive) all count as locked.

A file that does **not** contain a `[security]` section at all is not
considered a Gitea config and is not flagged — see `samples/good-3.txt`.

## How the detector decides

1. Locate the `[security]` section. If absent, the file is not a Gitea
   config; do not flag.
2. Within `[security]`, look for an `INSTALL_LOCK = <value>` assignment
   (case-insensitive on the key). Comment lines (`#`/`;`) do not count.
3. If a real assignment exists with a truthy value (`true` / `1` / `yes` /
   `on`) and no falsy assignment overrides it, the file is GOOD.
4. Otherwise (missing, falsy, or only commented) the file is BAD.

## Run the worked example

```sh
bash run-tests.sh
```

Expected output:

```
bad=4/4 good=0/4 PASS
```

The four bad fixtures cover: missing entirely, explicit `false`, only a
comment, and `0`. The four good fixtures cover: explicit `true`, mixed-case
`TRUE`, no `[security]` section at all, and `yes`.

## Run against your own files

```sh
bash detect.sh path/to/app.ini path/to/custom/conf/app.ini
# or via stdin:
cat app.ini | bash detect.sh
```

Exit code is `0` only if every `bad-*` sample is flagged and no `good-*`
sample is flagged, so this is safe to wire into CI as a defensive
misconfiguration gate for git-server deployments.
