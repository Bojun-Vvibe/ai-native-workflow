# llm-output-gotify-default-admin-pass-detector

Static lint that flags Gotify (`gotify/server`) `config.yml` files
that bootstrap the admin account with the default / weak password.

## Why this matters

On first boot Gotify reads `config.yml` (or env vars
`GOTIFY_DEFAULTUSER_NAME` / `GOTIFY_DEFAULTUSER_PASS`) and creates an
admin user. The official starter snippet — which is what almost every
LLM regurgitates — is:

```yaml
defaultuser:
  name: admin
  pass: admin
passstrength: 10
```

Anyone who can reach the HTTP listener can `POST /login` with those
credentials, get a session token, and then:

- read every message in every application stream (Gotify is a
  push-notification bus, often used for ops alerts that include
  hostnames, IPs, error stacks);
- create / delete users;
- rotate every client and application token, locking out legitimate
  callers.

Once an admin session is taken, recovery requires DB-level edits.

## What it catches

- `defaultuser.pass` set to a known weak / placeholder value
  (`admin`, `password`, `changeme`, `gotify`, `letmein`, `secret`,
  short numerics, `<TODO>`, empty string, …).
- `defaultuser.name: admin` paired with a `pass` shorter than 8
  characters.
- `defaultuser` block has `name` but no `pass` key — Gotify falls
  back to the bundled default `admin`.
- `passstrength: <8>` (bcrypt cost too low; some old releases also
  treated `0` as "no hashing").

## What it does NOT catch (yet)

- Env-var overrides (`GOTIFY_DEFAULTUSER_PASS`) supplied at runtime —
  this is a *config-file* lint.
- Strong-but-pwned passwords (no HIBP lookup; that would need
  network).
- Per-application tokens — those are minted at runtime, not in
  `config.yml`.

## Suppression

Add a top-of-file comment:

```yaml
# gotify-default-admin-allowed
```

## Usage

```
python3 detector.py path/to/config.yml
```

Exit code is the number of files with at least one finding (capped
at 255).

## Worked example

```
$ ./verify.sh
bad=4/4 good=0/3
PASS
```

## CWE refs

- CWE-798: Use of Hard-coded Credentials
- CWE-521: Weak Password Requirements
- CWE-1392: Use of Default Credentials
