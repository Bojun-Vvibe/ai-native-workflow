# llm-output-uptime-kuma-disable-auth-detector

Detect Uptime Kuma deployment snippets that ship with the
dashboard's authentication disabled.

Uptime Kuma supports a "no auth" mode that was intended only for
single-user kiosks behind a trusted reverse proxy. It can be
enabled three different ways, all of which LLMs reproduce:

1. Environment variable in `.env` / `docker-compose.yml`:
   ```
   UPTIME_KUMA_DISABLE_AUTH=true
   ```
   (also accepts `1`, `yes`, `on`).
2. CLI flag passed to `node server/server.js`, or via the docker
   `command:` / `entrypoint:` override:
   ```
   --disable-auth
   ```
3. Settings dump / restore JSON containing
   ```
   "disableAuth": true
   ```

When asked "give me an Uptime Kuma compose I can drop in" or
"I want a public status page without a login prompt", models
routinely:

- Add `UPTIME_KUMA_DISABLE_AUTH=true` to the rendered `.env` and
  publish `3001:3001` straight to the host with no proxy in
  front.
- Override the container `command:` to include `--disable-auth`
  while binding `0.0.0.0:3001`.
- Pre-seed a `data/kuma.db` JSON dump that already carries
  `"disableAuth": true`, so the dashboard comes up unauthenticated
  on first boot.

## Bad patterns

1. `UPTIME_KUMA_DISABLE_AUTH=true|1|yes|on` in a Kuma env file
   (dotenv form).
2. `UPTIME_KUMA_DISABLE_AUTH: true|1|yes|on` as a YAML mapping-
   form `environment:` entry inside a Kuma service.
3. `- UPTIME_KUMA_DISABLE_AUTH=true|...` as a YAML list-form
   `environment:` entry inside a Kuma service.
4. The `--disable-auth` flag in a Kuma `command:` / `entrypoint:`
   line, OR a settings-dump JSON with `"disableAuth": true`.

## Good patterns

- Variable absent entirely.
- Variable / setting explicitly false (`false`, `0`, `no`, `off`).
- File mentions the knob only inside a `#` comment.
- File is not an Uptime Kuma file (no `louislam/uptime-kuma`
  image reference, no `UPTIME_KUMA_*` env key, no Kuma settings-
  dump fingerprint such as `"uptimeKumaVersion"`,
  `"primaryBaseURL"`, or `"appName": "Uptime Kuma"`).

## Tests

```sh
./detect.sh samples/bad/* samples/good/*
```

Verified-runnable smoke output (verbatim):

```
BAD  samples/bad/01-dotenv-true.conf
BAD  samples/bad/02-compose-mapping-1.yml
BAD  samples/bad/03-compose-list-yes.yml
BAD  samples/bad/04-compose-command-flag.yml
GOOD samples/good/01-compose-auth-on.yml
GOOD samples/good/02-explicit-false.conf
GOOD samples/good/03-doc-comment-only.conf
GOOD samples/good/04-not-kuma.yml
bad=4/4 good=0/4 PASS
```

## Why this matters

The Uptime Kuma dashboard is not a thin status page. It is the
admin surface that holds:

- HTTP basic-auth credentials and bearer tokens for every
  monitored URL (HTTP, HTTPS, Keyword, JSON-Query monitors).
- MQTT username / password for MQTT monitors.
- Database connection strings for MariaDB / Postgres / MongoDB
  monitors.
- Push tokens for the `Push` monitor type.
- Notification provider credentials (Slack webhook URLs, Discord
  webhook URLs, Pushover keys, Telegram bot tokens, generic
  webhook secrets, Gotify keys, ntfy auth, SMTP creds).
- The status-page admin role, including the ability to add
  arbitrary HTML / JS into the public status page.

Each saved secret has a one-click "Reveal" button in the UI that
prints the cleartext value back to the browser. Disabling auth
means anyone who can reach port 3001 can:

- Read all of the above secrets in cleartext.
- Edit any monitor — point a "HTTP Keyword" monitor at an
  attacker-controlled URL with the original Authorization header
  to exfiltrate that header to the attacker's logs.
- Inject HTML / JS into the public status page that the
  organisation links from its docs.
- Add a new notification target (their own webhook) and trigger
  an alert to receive callbacks signed with the stored secret.

The intended deployment is:

- Bind Kuma to `127.0.0.1` (or a private network) and put a
  reverse proxy in front that performs its own authentication.
- Leave `UPTIME_KUMA_DISABLE_AUTH` unset so the built-in login
  remains active as a defence-in-depth layer.
- Treat the SQLite DB as secret material; backups go to the same
  vault as the notification secrets they contain.

What LLMs reproduce is the lazy "demo" path: `--disable-auth` so
the user does not have to remember a password, plus
`ports: - "3001:3001"` so it is reachable on the LAN. The detector
catches all three knob shapes in one pass.

The detector is deliberately narrow:

- Requires a Kuma scope fingerprint (a `louislam/uptime-kuma`
  image, a `UPTIME_KUMA_*` env key, or a Kuma settings-dump
  fingerprint). A bare `--disable-auth` flag in some unrelated
  tool's command line does not fire.
- Strips `#` line comments before scanning so commented-out
  examples do not false-fire.
- Recognises all three knob shapes (env var, CLI flag, settings
  JSON) so the operator cannot accidentally side-step one branch.

Bash 3.2+ / awk / coreutils only. No network calls.
