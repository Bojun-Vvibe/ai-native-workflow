# llm-output-gitea-install-lock-missing-detector

Detect Gitea `app.ini` (or environment-equivalent) configurations that
LLMs emit with the install wizard left unlocked. Gitea's first-run web
installer at `/install` is gated by exactly one switch:

```
[security]
INSTALL_LOCK = true
```

When that key is absent or set to `false`, the install endpoint stays
live and reachable on the public listener — anyone who hits `/install`
can reset the admin account, point the DB anywhere, and own the
instance. Because the official docker-compose / helm "quick start"
snippets often delegate this to the user's first browser visit, models
hallucinate that "Gitea will lock itself" and routinely emit configs
that never set the key at all.

## Bad patterns (any one is sufficient on a snippet that *is* a Gitea
config — see scope)

1. `[security]` section present but no `INSTALL_LOCK` key.
2. `INSTALL_LOCK = false` (any case, with or without spaces, with or
   without surrounding quotes).
3. Env-var form `GITEA__SECURITY__INSTALL_LOCK=false` (or unset while
   other `GITEA__*` env vars are set, indicating an env-driven config
   that forgot the lock).
4. A docker-compose / helm `environment:` block for `gitea/gitea`
   that sets `GITEA__*` keys but never sets
   `GITEA__SECURITY__INSTALL_LOCK`.

## Good patterns

- `[security]` with `INSTALL_LOCK = true`.
- `GITEA__SECURITY__INSTALL_LOCK=true` in env.
- Snippets that don't actually configure Gitea (out of scope, not
  flagged).

## Scope fingerprint

We only inspect a snippet if it looks like a Gitea config. Triggers:

- Any line matching `gitea/gitea` (image), `gitea.io`, an INI section
  header `[security]` / `[server]` / `[database]` adjacent to a
  Gitea-specific key (`APP_NAME`, `RUN_USER`, `ROOT_URL`, `DOMAIN`
  inside `[server]`), or any `GITEA__` env var.

This avoids flagging arbitrary INI files that happen to have a
`[security]` section.

## False-positive notes

- We do not flag generic INI files. A `[security]` section without
  any other Gitea fingerprint is ignored.
- `INSTALL_LOCK = 1` is treated as true (Gitea accepts it).
- A snippet that documents the *removal* of the lock (e.g., a
  comment) but actually sets `INSTALL_LOCK = true` is good — we
  strip `;` and `#` comments before scanning.
