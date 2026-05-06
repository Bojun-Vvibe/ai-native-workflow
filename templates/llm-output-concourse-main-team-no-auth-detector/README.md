# llm-output-concourse-main-team-no-auth-detector

Detect Concourse CI `web` node configurations that LLMs commonly emit
with the `main` team left effectively unauthenticated. The `main`
team in Concourse is the bootstrap admin team — it owns every other
team and pipeline. If its auth is misconfigured, the entire cluster
is open.

When asked "set up Concourse" / "give me a `docker-compose.yml` for
Concourse" / "start the Concourse web node", models routinely:

- Pass `--main-team-local-user=admin` (or an env var equivalent like
  `CONCOURSE_MAIN_TEAM_LOCAL_USER=admin`) without ever defining that
  local user via `--add-local-user`.
- Define the local user with a placeholder password
  (`--add-local-user=admin:admin`, `:password`, `:changeme`,
  `:concourse`, `:please_change_me`, empty value `:`).
- Start the web node with **no** auth flags at all
  (no `--main-team-*`, no `--add-local-user`, no `--main-team-github-*`,
  no `--main-team-oauth-*`, no `--main-team-cf-*`, no
  `--main-team-ldap-*`). Concourse will refuse to start in some
  versions, but several upstream "quick start" snippets disable that
  via `CONCOURSE_ENABLE_NOAUTH_MAIN_TEAM=true` or
  `--enable-noauth-main-team`. We flag any explicit "no auth on main
  team" toggle.

## Bad patterns

1. CLI / env: `--main-team-local-user=<name>` (or
   `CONCOURSE_MAIN_TEAM_LOCAL_USER=<name>`) with **no**
   `--add-local-user=<name>:...` (or `CONCOURSE_ADD_LOCAL_USER`)
   defining that user anywhere in the same config.
2. CLI / env: `--add-local-user=<name>:<password>` (or env equivalent)
   where `<password>` is empty or one of the well-known placeholder
   passwords (`admin`, `password`, `concourse`, `changeme`,
   `please_change_me`, `test`, `secret`, `123456`).
3. CLI / env: `--enable-noauth-main-team` /
   `CONCOURSE_ENABLE_NOAUTH_MAIN_TEAM=true` set explicitly.

## Good patterns

- `--add-local-user=admin:<long random>` plus
  `--main-team-local-user=admin`, where the password is not a known
  placeholder and is at least 12 characters.
- `--main-team-github-org=<org>` (or any of the OAuth/SAML/LDAP
  `--main-team-*` flags) plus the matching auth provider flags. We do
  not flag these — Concourse handles them via its own provider.
- A `web` invocation that wires the `main` team to a non-local IdP
  and never sets `--enable-noauth-main-team`.

## Scope

Targets `concourse web` invocations: shell scripts, Dockerfiles,
docker-compose `command:` blocks, env-only configs (`environment:`),
and systemd unit `ExecStart` lines. Worker (`concourse worker`) is
out of scope — workers authenticate via TSA keys, not team auth.

## False-positive notes

- A snippet that only references `concourse worker` is ignored.
- A snippet that defines `--add-local-user` with a strong password
  but **also** declares `--main-team-local-user` for a *different*
  username is flagged as "user referenced but not defined". This is
  intentional — that misconfig blocks the team in some versions and
  silently leaves it open in others, depending on version.
- We do not parse YAML structure; we scan for the canonical CLI
  flags and `CONCOURSE_*` env keys. Helm charts that set
  `web.env.CONCOURSE_ADD_LOCAL_USER` will be detected.
