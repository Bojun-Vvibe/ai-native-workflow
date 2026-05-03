# llm-output-superset-secret-key-default-detector

Stdlib-only Python detector that flags **Apache Superset**
configurations that leave `SECRET_KEY` at the upstream default
(`\\2dEDC3MOdPRJHsJ`), the docker-compose-non-dev placeholder
(`TEST_NON_DEV_SECRET`), or any of the LLM-favourite filler
strings (`changeme`, `your_secret_key_here`, `superset`, ...).

Maps to **CWE-798** (Use of Hard-coded Credentials) and
**CWE-1188** (Insecure Default Initialization of Resource).

## Why this matters

Superset uses Flask's `SECRET_KEY` for three security-critical
jobs:

1. signing session cookies (Flask `itsdangerous`),
2. signing the CSRF token,
3. as the Fernet root key that encrypts database-connection URIs
   stored in the metadata DB column `encrypted_extra`.

If `SECRET_KEY` is a value an attacker can guess — e.g. the
upstream example `\\2dEDC3MOdPRJHsJ` or the
`TEST_NON_DEV_SECRET` from `docker/.env-non-dev` — they can:

- forge a session cookie claiming the `Admin` role and walk into
  the dashboard with full read/write/SQL Lab access (CVE-class:
  pre-auth → admin),
- mint a valid CSRF token for any state-changing request,
- decrypt every stored `encrypted_extra` blob, exposing prod
  warehouse credentials (Snowflake, BigQuery, Postgres, ...).

The upstream Superset repo has shipped explicit warnings about
this for years, including on the docker `.env-non-dev` file:

    # SUPERSET_SECRET_KEY = a long random string used by Superset
    # for security relevant operations. CHANGE THIS!

LLMs nevertheless reach for the placeholder verbatim, because it
is the literal example in `superset_config.py.example` and in
every quickstart blog post.

## Heuristic

We flag, outside `#` / `//` comments:

1. `SECRET_KEY = "<known-weak>"` (also `SECRET_KEY: str = ...`)
   in any `*.py` (`superset_config.py` is the canonical filename).
2. `SUPERSET_SECRET_KEY=<known-weak>` in `.env`, `.env-non-dev`,
   Compose, Dockerfile, or Helm values YAML.
3. Helm CLI form: `--set superset.secretKey=<known-weak>`.

Known-weak set (case-insensitive):

    \\2dEDC3MOdPRJHsJ           # upstream config example
    TEST_NON_DEV_SECRET         # upstream docker .env-non-dev
    your_secret_key_here        # LLM placeholder favourite
    changeme / change_me / change-me
    secret
    superset
    please_change_me_in_production
    thisisnotasecret
    default_secret
    supersecret
    mysecretkey

Each occurrence emits one finding line.

## What we flag

- `SECRET_KEY = "\\2dEDC3MOdPRJHsJ"` in `superset_config.py`.
- `SUPERSET_SECRET_KEY=TEST_NON_DEV_SECRET` in `.env-non-dev`.
- `SUPERSET_SECRET_KEY: "changeme"` inside a Compose
  `environment:` block.
- `--set superset.secretKey=your_secret_key_here` in a Helm
  install command.

## What we accept

- `SECRET_KEY = os.environ["SUPERSET_SECRET_KEY"]` (sourced from env).
- `SECRET_KEY = secrets.token_urlsafe(64)` at boot.
- `SUPERSET_SECRET_KEY` whose value is a 40+ char random string
  not in the known-weak set.
- Comment-only mentions:
  `# do NOT keep SECRET_KEY = "changeme" in production`.

## CWE / standards

- **CWE-798**: Use of Hard-coded Credentials.
- **CWE-1188**: Insecure Default Initialization of Resource.
- **CWE-330**: Use of Insufficiently Random Values (downstream
  effect on every Fernet-encrypted column).
- Apache Superset config docs:
  > SECRET_KEY: Make sure you set this to a long random string.
  > Do not use the default.

## Usage

```bash
python3 detect.py path/to/superset_config.py
python3 detect.py path/to/repo/
```

Exit codes: `0` = no findings, `1` = findings (printed to stdout),
`2` = usage error.

## Smoke test

```
$ bash smoke.sh
bad=4/4 good=0/3
PASS
```

Layout:

```
examples/bad/
  01_superset_config_upstream.py   # upstream \\2dEDC3MOdPRJHsJ
  02_env_non_dev_default.env.example  # SUPERSET_SECRET_KEY=TEST_NON_DEV_SECRET
  03_compose_environment_block.yml # Compose env block, "changeme"
  04_helm_set_cli.sh               # helm upgrade --set ...secretKey=...
examples/good/
  01_superset_config_from_env.py   # SECRET_KEY from env
  02_env_random_value.env.example  # 64-char random secret
  03_helm_secretref.yaml           # secret pulled from secretKeyRef
```

## Limits / known false negatives

- Programmatic builds (e.g. `SECRET_KEY = "pre" + "fix"`) are out
  of scope; we only see literal string assignments.
- We do not inspect entropy of the value — only membership in the
  known-weak set. A short but novel string like `"abc"` will pass;
  pair this detector with an entropy-based secret scanner for
  full coverage.
- Sibling detectors in this series cover Superset
  `WTF_CSRF_ENABLED=False`, `TALISMAN_ENABLED=False`, and public
  metadata-db exposure.
