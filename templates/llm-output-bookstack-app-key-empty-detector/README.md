# llm-output-bookstack-app-key-empty-detector

Detect BookStack configurations that LLMs commonly emit with the
Laravel `APP_KEY` left empty, set to the literal upstream placeholder,
or set to a non-base64 string. BookStack inherits Laravel's encryption
contract: `APP_KEY` keys cookie signing, session encryption, and any
`Crypt::` / `encrypted` cast field. An empty or known key lets an
attacker forge session cookies and decrypt anything BookStack stored
encrypted.

When asked "set up BookStack" / "give me a BookStack `.env` /
docker-compose / Helm values", models routinely:

- Leave `APP_KEY=` blank and tell the user to run
  `php artisan key:generate` "later".
- Hard-code `APP_KEY=SomeRandomString` or `APP_KEY=changeme` —
  Laravel accepts the value but the cipher (AES-256-CBC) requires
  exactly 32 raw bytes, so this either crashes or, more dangerously,
  some forks/ports silently fall back to a derived key.
- Hard-code `APP_KEY=base64:` (literal `base64:` prefix and nothing
  after).
- Copy the example value `APP_KEY=base64:SomeRandomKeyGoesHere` /
  `base64:GENERATE_THIS_KEY` straight from a tutorial.

## Bad patterns

1. Any line of the form `APP_KEY=` followed by nothing (or only
   whitespace / quotes).
2. `APP_KEY=base64:` with no payload after the colon.
3. `APP_KEY=base64:<payload>` where `<payload>` decodes to fewer than
   32 bytes — i.e. the placeholder is too short to be a real AES-256
   key. We do not fully base64-decode; we approximate by checking the
   payload length (a base64-encoded 32-byte string is 44 chars
   including padding).
4. `APP_KEY=<value>` where `<value>` is a known placeholder string
   (`changeme`, `please_change_me`, `SomeRandomString`,
   `SomeRandomKeyGoesHere`, `GENERATE_THIS_KEY`,
   `your_app_key_here`, `secret`), case-insensitive.

## Good patterns

- `APP_KEY=base64:<44-char base64>` with a real payload.
- A config that does not set `APP_KEY` at all but **also** does not
  reference BookStack/Laravel — out of scope, not flagged.
- A docker-compose that injects `APP_KEY` from an external secret
  file or env reference (`APP_KEY=${BOOKSTACK_APP_KEY}` style) — we
  do not flag unresolved env references because the actual value is
  out of scope of the file we're scanning.

## Scope

Targets BookStack `.env`-style files (we use `.conf` extension in
fixtures to satisfy repo policy that bans `.env*` filenames),
docker-compose YAML with `environment:` blocks, Kubernetes Secret
manifests, and Helm values. We require the file to mention BookStack
**or** to set BookStack-specific keys (`APP_URL` + `DB_DATABASE` +
`MAIL_FROM_NAME` is too generic; we look for `bookstack` literal or
the canonical pair `APP_KEY` + `APP_URL` co-located).

## False-positive notes

- A config that sets `APP_KEY=${SOME_VAR}` is not flagged — the
  template variable is the secret indirection.
- Plain Laravel apps (not BookStack) trip the same Laravel rule;
  this detector intentionally narrows on BookStack signals to keep
  scope focused.
