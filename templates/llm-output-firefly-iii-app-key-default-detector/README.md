# llm-output-firefly-iii-app-key-default-detector

Detect Firefly III environment / docker-compose snippets that ship
with `APP_KEY` left at the well-known placeholder string from the
official `.env.example` and the `docker-compose.yml` template:

```
APP_KEY=SomeRandomStringOf32CharsExactly
```

Firefly III is a Laravel app. `APP_KEY` is the symmetric key used
by Laravel's `encrypt()` / `decrypt()` and by the cookie / session
encrypter. If two installations share the same key:

- session cookies issued by one install are decryptable and
  forgeable by anyone who has that key — i.e. anyone who has read
  the public docs;
- DB columns Laravel encrypts at rest (webhook secrets, OAuth
  tokens, personal access tokens stored by Firefly III's importers)
  decrypt with the same key.

When asked "spin up Firefly III with docker-compose" or "give me
a working `.env` for Firefly III", models routinely:

- Copy the literal `APP_KEY=SomeRandomStringOf32CharsExactly`
  line out of the README into the rendered `.env`.
- Substitute it with another obvious placeholder
  (`ChangeMeChangeMe`, `your-app-key-here`, `xxxxxxxxxxxxxxxx`).
- Render the same placeholder inside a `docker-compose.yml`
  `environment:` block, mapping or list form.

## Bad patterns

1. `APP_KEY=SomeRandomStringOf32CharsExactly` — the literal docs
   placeholder.
2. `APP_KEY=<placeholder-like value>` — `ChangeMe...`,
   `your-app-key-here`, `please-change-this`, `placeholder`,
   `example-key`, etc.
3. `APP_KEY=<single character repeated 16+ times>` —
   `xxxxxxxxxxxxxxxx`, `0000000000000000`, `aaaaaaaaaaaaaaaa`.
4. The same patterns as a YAML mapping-form or list-form
   `environment:` entry inside a Firefly III service.

## Good patterns

- `APP_KEY` absent — Firefly III generates one on first boot via
  `php artisan key:generate`.
- `APP_KEY=` explicitly empty.
- `APP_KEY=<32+ char mixed-case+digits random string>` that does
  not match any placeholder pattern.
- File mentions `APP_KEY` only inside a `#` comment.
- File is not a Firefly III file (no Firefly image reference, no
  Firefly-specific env keys like `SITE_OWNER`, `STATIC_CRON_TOKEN`,
  `FIREFLY_III_*`, `TRUSTED_PROXIES`).

## Tests

```sh
./detect.sh samples/bad/* samples/good/*
```

Verified-runnable smoke output (verbatim):

```
BAD  samples/bad/01-dotenv-literal-placeholder.conf
BAD  samples/bad/02-compose-mapping-changeme.yml
BAD  samples/bad/03-compose-list-form-xxxx.yml
BAD  samples/bad/04-dotenv-your-app-key-here.conf
GOOD samples/good/01-real-random-key.conf
GOOD samples/good/02-app-key-absent.conf
GOOD samples/good/03-doc-comment-only.conf
GOOD samples/good/04-not-firefly.conf
bad=4/4 good=0/4 PASS
```

## Why this matters

Firefly III holds personal financial data: bank balances, account
numbers, recurring transfer rules, payee names, OAuth refresh
tokens for bank-import bridges, and webhook secrets that fire on
every transaction. The Laravel session middleware authenticates
every request by decrypting the session cookie with `APP_KEY`. If
the key is the documented placeholder:

- Every Firefly III instance that ran with the placeholder shares
  the same key. An attacker can mint a session cookie offline for
  any user ID and use it against any such instance.
- Encrypted DB columns — webhook secrets, third-party API tokens
  imported via the bank-bridge integrations — decrypt with the
  same key. A single dump leak (DB backup, accidental S3 bucket,
  developer laptop) yields the cleartext secrets.
- Laravel's `php artisan tinker` examples in support threads run
  with the placeholder by default, so test snippets posted to
  GitHub issues sometimes include data still encrypted under it.

The intended deployment is:

- Generate a 32-byte random key with `php artisan key:generate`
  (or `openssl rand -base64 32`) before the first `up`.
- Store the key out of band (sealed secret, vault, password
  manager), not in the same git repo as `docker-compose.yml`.
- Treat key rotation as a session-invalidation event.

What LLMs reproduce is the README literally: the placeholder
string ends up in the rendered `.env`, the user runs
`docker compose up -d`, Firefly boots happily, and the
deployment is now key-equivalent to every other LLM-bootstrapped
Firefly III on the public internet.

The detector is deliberately narrow:

- Requires a Firefly scope fingerprint (a `fireflyiii/core` /
  `jc5x/firefly-iii` image, or a Firefly-specific env key like
  `SITE_OWNER`, `STATIC_CRON_TOKEN`, `FIREFLY_III_*`,
  `TRUSTED_PROXIES`). A bare `APP_KEY=...` line in some unrelated
  Laravel app does not fire.
- Strips `#` line comments before scanning so commented-out
  examples do not false-fire.
- Treats only the documented placeholder + a small denylist of
  obvious stand-ins + 16+-char single-character runs as bad. A
  real-looking random value is accepted; we deliberately do not
  try to enforce true cryptographic strength here, only catch the
  copy-paste-from-README failure mode that LLMs produce.

Bash 3.2+ / awk / coreutils only. No network calls.
