# llm-output-strapi-admin-jwt-secret-default-detector

Detect Strapi config / `.env` snippets emitted by LLMs that ship the
quickstart placeholder values for `ADMIN_JWT_SECRET`, `API_TOKEN_SALT`,
`JWT_SECRET`, `APP_KEYS`, or `TRANSFER_TOKEN_SALT`.

## Why it matters

Strapi v4/v5 expects four (now five) per-environment secrets. The
official quickstart and many tutorials demo them with literal
placeholder strings like `tobemodified`, `aSecretSalt`,
`toBeModified1`, `changeme`. LLMs paste those literals straight into
`config/admin.js`, `config/server.js`, `config/plugins.js`, or
`.env` examples. Any Strapi instance running with those defaults can
have admin or end-user JWTs minted by anyone who knows the literal -
which is everyone, since the values are in the public docs.

## Rules

| # | Pattern | Why it matters |
|---|---------|----------------|
| 1 | `secret: env('ADMIN_JWT_SECRET', 'tobemodified')` (or any object-style `secret`/`salt`/`jwtSecret` with a known placeholder default) | Anyone can mint admin JWTs |
| 2 | `.env`-style `ADMIN_JWT_SECRET=tobemodified` (also `API_TOKEN_SALT`, `JWT_SECRET`, `TRANSFER_TOKEN_SALT`) | Same exposure via env file |
| 3 | `users-permissions` plugin config with `jwtSecret: 'changeme'` | End-user JWT signing key is public |
| 4 | `app.keys: ['toBeModified1', 'toBeModified2']` (or `APP_KEYS=toBeModified1,toBeModified2`) | Session signing keys are public |

Recognised placeholders: `tobemodified`, `tobemodified1..4`,
`changeme`, `please-change-me`, `replaceme`, `yourSecretKey`,
`mySecret`, `secretKey`, `somethingSecret`, `aSecretSalt`,
`myJwtSecret`, `test`, `secret`, `default`, `example`, `placeholder`,
`xxx`/`xxxx`/`xxxxx`, `todo`, and common variants.

`#` and `//` comments are stripped before matching, so a doc that
*warns* against the insecure default does not trigger.

## Suppression

Add `# strapi-default-secret-ok` anywhere in the file to disable all
rules (e.g. an example in onboarding docs).

## Usage

```bash
python3 detector.py path/to/config/admin.js
python3 detector.py .env
```

Exit code = number of files with at least one finding.

## Tests

```bash
python3 run_tests.py
```

Runs the detector against `examples/bad/*` (must all flag) and
`examples/good/*` (must all pass clean), printing
`PASS bad=4/4 good=0/3` on success.
