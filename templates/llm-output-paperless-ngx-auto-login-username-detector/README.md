# llm-output-paperless-ngx-auto-login-username-detector

Detect Paperless-NGX environment / docker-compose snippets that
set `PAPERLESS_AUTO_LOGIN_USERNAME` to a non-empty value. That
variable was added to ease reverse-proxy SSO setups and tells the
Paperless web app: "skip the login form, treat every incoming
request as user X". Paperless-NGX performs **no check** that the
request actually arrived through a trusted proxy — if the web
port is reachable directly (LAN, host network, exposed port), the
auto-login fires for every request, including admin actions if
the configured user has `is_staff` / `is_superuser`.

When asked "set up Paperless behind my proxy without a login
prompt" or "how do I auto-login as admin in Paperless", models
routinely:

- Render `PAPERLESS_AUTO_LOGIN_USERNAME=admin` in the project's
  `.env` and ship the compose file with `ports: - "8000:8000"`,
  i.e. directly bound to the host.
- Drop `PAPERLESS_AUTO_LOGIN_USERNAME: <user>` into a
  `docker-compose.yml` `environment:` block without any proxy in
  front of the service.
- Use the YAML list-form (`- PAPERLESS_AUTO_LOGIN_USERNAME=root`)
  inside the same compose file that exposes port 8000 to `0.0.0.0`.
- Pre-fill the `paperless.conf` shipped in the official template
  with `PAPERLESS_AUTO_LOGIN_USERNAME = "paperless"`.

## Bad patterns

1. `PAPERLESS_AUTO_LOGIN_USERNAME=<non-empty>` in a Paperless
   env file (`.env`, `paperless.conf`, `docker-compose.env`).
2. `PAPERLESS_AUTO_LOGIN_USERNAME: <non-empty>` as a YAML
   mapping-form `environment:` entry inside a Paperless service.
3. `- PAPERLESS_AUTO_LOGIN_USERNAME=<non-empty>` as a YAML
   list-form environment entry inside a Paperless service.
4. The same in `paperless.conf` style with quoted value
   (`PAPERLESS_AUTO_LOGIN_USERNAME = "paperless"`).

## Good patterns

- Variable absent entirely.
- Variable explicitly empty (`PAPERLESS_AUTO_LOGIN_USERNAME=`).
- File mentions the variable only inside a `#` comment.
- File is not a Paperless file at all (no `PAPERLESS_*` scope
  keys and no `paperless` / `paperless-ngx` image reference).

## Tests

```sh
./detect.sh samples/bad/* samples/good/*
```

Verified-runnable smoke output (verbatim):

```
BAD  samples/bad/01-dotenv-admin.conf
BAD  samples/bad/02-compose-mapping.yml
BAD  samples/bad/03-compose-list-form.yml
BAD  samples/bad/04-paperless-conf-quoted.conf
GOOD samples/good/01-no-auto-login.conf
GOOD samples/good/02-explicitly-empty.conf
GOOD samples/good/03-doc-comment-only.conf
GOOD samples/good/04-not-paperless.conf
bad=4/4 good=0/4 PASS
```

## Why this matters

Paperless-NGX stores scanned documents — invoices, tax records,
contracts, IDs, prescriptions. The user accounts in it map onto a
permissions model (per-document ownership, per-tag visibility,
share links, API tokens). `PAPERLESS_AUTO_LOGIN_USERNAME` short-
circuits that model: every request is silently identified as the
configured user, and the web framework's session middleware sees a
fully authenticated session.

The intended deployment is:

- A reverse proxy (nginx / Traefik / Caddy) terminates TLS,
  authenticates the caller (mTLS, OIDC, basic auth, etc.), and
  only then forwards to Paperless on a non-public port.
- Paperless trusts the proxy because nothing else can reach it.

What LLMs reproduce is:

- Compose file that publishes `8000:8000` straight to the host.
- `PAPERLESS_AUTO_LOGIN_USERNAME=admin` in the env file.
- No proxy at all, or a proxy that does not authenticate.

Anyone who can reach port 8000 — local network, mis-configured
firewall, exposed docker port on a cloud VM — gets the admin
session for free, including the `/api/documents/` endpoints that
return raw uploaded files and the `/admin/` Django site that lets
them create new superusers.

The detector is deliberately narrow:

- Requires a Paperless scope fingerprint (a `PAPERLESS_*` key
  other than the auto-login one, or an `image:` line referencing
  `paperless` / `paperless-ngx`). A bare line in some unrelated
  env file does not fire.
- Strips `#` line comments before scanning so commented-out
  examples do not false-fire.
- Treats any non-empty value as bad; we deliberately do not try
  to whitelist "service account" names because the safe pattern
  is "do not set this variable when the proxy is not in scope".

Bash 3.2+ / awk / coreutils only. No network calls.
