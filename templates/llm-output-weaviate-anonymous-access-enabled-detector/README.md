# llm-output-weaviate-anonymous-access-enabled-detector

Stdlib-only Python detector that flags **Weaviate** vector-database
deployments that enable
`AUTHENTICATION_ANONYMOUS_ACCESS_ENABLED=true` *and* leave every
other authentication module disabled (no API key, no OIDC).

Maps to **CWE-306** (Missing Authentication for Critical Function)
and **CWE-1188** (Insecure Default Initialization of Resource).

## Why this matters

Weaviate exposes both REST (`/v1/...`) and GraphQL (`/v1/graphql`)
endpoints that can read, write, and reshape the entire vector
store and class schema. With anonymous access on and no auth
module enabled, any caller that can reach port 8080 has effective
`Admin` privileges:

- enumerate every class and inspect/exfiltrate every vector,
- delete or replace any object,
- create new classes with attacker-controlled vectorizer modules,
- in some configurations, trigger outbound calls to attacker-
  chosen vectorizer endpoints.

The official Weaviate quickstart docker-compose ships exactly this
configuration so the embedded "Try it out" demo works without
prompting for credentials. LLMs reproduce that block verbatim
when asked for "a docker-compose to run Weaviate locally" and the
operator then deploys it to a public host.

## Heuristic

We flag, outside `#` / `//` comments, any line that sets
`AUTHENTICATION_ANONYMOUS_ACCESS_ENABLED` to a truthy value
(`true`, `True`, `1`, `yes`, `on`) when the same file does **not**
also enable one of:

    AUTHENTICATION_APIKEY_ENABLED=true
    AUTHENTICATION_OIDC_ENABLED=true

Forms recognized:

1. Compose / YAML `KEY: 'true'`.
2. `.env` / shell `KEY=true` (with optional `export`).
3. Helm CLI `--set ...AUTHENTICATION_ANONYMOUS_ACCESS_ENABLED=true`.
4. Helm values nested form
   `authentication.anonymous_access.enabled: true`.

## Usage

    python3 detect.py path/to/file_or_dir [more...]

Exit codes: `0` no findings, `1` findings, `2` usage error.

## Verified worked example

The `examples/` tree contains 4 bad fixtures (compose, env-file,
shell script, helm values) and 3 good fixtures (compose with
APIKEY also enabled, env-file with anonymous off + OIDC on, helm
values with anonymous off + apikey on). Run:

    bash smoke.sh

Expected output:

    bad=4/4 good=0/3
    PASS

## Remediation

- Set `AUTHENTICATION_ANONYMOUS_ACCESS_ENABLED=false` for any
  internet-reachable Weaviate instance.
- If you need a public read-only demo, leave anonymous on **and**
  enable `AUTHENTICATION_APIKEY_ENABLED=true` with a
  `AUTHORIZATION_ADMINLIST_USERS` list that restricts mutation to
  named identities.
- For production, prefer OIDC
  (`AUTHENTICATION_OIDC_ENABLED=true`) wired to your IdP.

## Mapping

- CWE-306 — Missing Authentication for Critical Function.
- CWE-1188 — Insecure Default Initialization of Resource.
