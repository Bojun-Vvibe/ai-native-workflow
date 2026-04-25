# structured-log-redactor

Recursive secret / PII scrubber for **already-recorded JSON logs**, run
at the trust boundary between "where the log was written" and
"wherever it's about to go" — a SaaS log backend, a bug-report
attachment, an analytics export, a copy on a developer's laptop. The
post-hoc, log-pipeline-side companion of
[`prompt-pii-redactor`](../prompt-pii-redactor/) (prompt-side, before
a model sees the input) and
[`tool-output-redactor`](../tool-output-redactor/) (tool-side, before
the agent sees the output).

Stdlib-only. Pure: returns a new object, never mutates input. Safe to
re-run (the markers are stable strings; redacting an already-redacted
record produces an equal output).

## Two complementary mechanisms

* **Sensitive-key redaction.** Any dict key whose **name** matches the
  case-insensitive `sensitive_keys` set has its **value** replaced
  wholesale with `"<REDACTED:keyname>"`. The match is on the key the
  value is *bound to*, not on the value itself; this catches a
  400-byte JWT bound to `"authorization"` even when the JWT happens
  to contain nothing pattern-matchable. Default set covers the
  obvious ones (`authorization`, `password`, `secret`, `api_key`,
  `cookie`, `*_token`, `client_secret`, `private_key`, `ssh_key`,
  `session`).
* **Regex value redaction.** Every string leaf is scanned with a
  pinned set of high-precision patterns. Default set: AWS access
  keys (`AKIA…` and friends), GitHub classic + fine-grained PATs,
  Slack tokens (`xox[baprs]-…`), JWTs (three base64url segments),
  RFC-5322-ish emails, IPv4 addresses. Each match is replaced with
  a typed marker — `<REDACTED:aws_access_key>`, `<REDACTED:jwt>`,
  etc. — so the redacted log is still skimmable for *which class of
  secret* was here without leaking the value or even a hash of it.

## Why no "smart" PII detection

ML name-detection / address-detection / "smart" classifiers are
intentionally out of scope:

* **False positives change meaning.** A function called `Mark`,
  a city called `Apple`, an enum value called `Andrews` — a
  detector that scrubs them silently corrupts the log.
* **False negatives are worse than no detection.** They lull the
  operator into trusting the redactor for things it cannot do, and
  the next leaked log line gets shipped under "we run the redactor
  on everything".

The redactor only redacts shapes with **high enough precision that a
match almost certainly *is* the thing**. If you have a domain-specific
secret shape, add it to `raw_patterns`; if you have a domain-specific
sensitive field name, add it to `sensitive_keys`.

## Why no value-based redaction of numbers

A 16-digit number can be a bank card number or a build id or a
nanosecond timestamp; the redactor cannot tell. Numeric secrets must
be bound to a sensitive *key* (`card_number`, `account_id`) and let
the key-name layer catch them.

## When to use it

* Shipping JSONL logs to a SaaS log backend that lives outside the
  current trust boundary.
* Producing a bug-report tarball that will be attached to a public
  issue.
* Exporting an agent trace to be replayed on a teammate's laptop.
* Sanitising the output of `tool-call-replay-log` before sharing.

## When NOT to use it

* As your *only* line of defense against secret leakage. Secrets
  should not be in logs in the first place; this is a belt-and-braces
  layer, not a primary control. Pair with an environment that refuses
  to log values bound to known-sensitive keys at write time.
* For binary data. The redactor only walks strings and JSON-shaped
  Python objects; it will not look inside a base64-encoded blob (and
  the patterns would not match base64-wrapped secrets anyway).
* For free-form natural-language text where you need *semantic* PII
  detection (names, addresses, ages). Use a real classifier; this
  template will silently miss them.

## Sample run

```
$ python3 worked_example.py
=== structured-log-redactor worked example ===

[1] sensitive-key redaction
{
  "Authorization": "<REDACTED:authorization>",
  "body": {
    "config": {
      "client_secret": "<REDACTED:client_secret>"
    },
    "password": "<REDACTED:password>",
    "user": "agent-42"
  },
  "headers": {
    "cookie": "<REDACTED:cookie>",
    "user-agent": "curl/8.6.0",
    "x-api-key": "<REDACTED:x-api-key>"
  },
  "items": [
    null,
    1,
    2.5,
    "plain"
  ],
  "ok": true,
  "request_id": "req-7714",
  "retries": 0
}

[2] regex value redaction in free text
{
  "event": "upload_failed",
  "msg": "Failed to upload artifact for build-77. AWS id <REDACTED:aws_access_key> rotated; new GitHub PAT <REDACTED:github_pat> replaces the old one. Slack alert sent via <REDACTED:slack_token>. JWT in transit: <REDACTED:jwt> \u2014 owner <REDACTED:email> from <REDACTED:ipv4>."
}

[3] stream-mode JSONL redaction
    {"level": "info", "msg": "no secrets here"}
    2026-04-25T10:00:00Z syslog-style line, not JSON — should pass through
    {"authorization": "<REDACTED:authorization>", "ip": "<REDACTED:ipv4>", "level": "warn"}

[4] idempotency: re-redacting an already-redacted record
    once  = {'authorization': '<REDACTED:authorization>', 'msg': 'ip <REDACTED:ipv4>'}
    twice = {'authorization': '<REDACTED:authorization>', 'msg': 'ip <REDACTED:ipv4>'}

[final stats]
{
  "keys_redacted": {
    "authorization": 4,
    "client_secret": 1,
    "cookie": 1,
    "password": 1,
    "x-api-key": 1
  },
  "patterns_redacted": {
    "aws_access_key": 1,
    "email": 1,
    "github_pat": 1,
    "ipv4": 3,
    "jwt": 1,
    "slack_token": 1
  },
  "records_processed": 6
}
```

Note the `keys_redacted: authorization: 4` count — that adds up across
all six processed records (one in [1], one in [3], two in [4]). The
stats survive across calls so the operator can answer "how much did we
redact in this batch?" without re-walking the log.

## Composes with

* [`prompt-pii-redactor`](../prompt-pii-redactor/) — *prompt-side*
  redaction before the model sees the input. Different trust boundary,
  same threat model.
* [`tool-output-redactor`](../tool-output-redactor/) — *tool-side*
  redaction before the agent sees the result. Different again.
* [`agent-trace-redaction-rules`](../agent-trace-redaction-rules/) —
  the *policy* document that tells you which fields go in
  `sensitive_keys` for an agent-trace log specifically.
* [`tool-call-replay-log`](../tool-call-replay-log/) — durable,
  fingerprinted tool-call log; redact a copy of the JSONL with this
  template *before* attaching it to a bug report or sharing across
  trust boundaries.
