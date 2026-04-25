# prompt-pii-redactor

Pre-flight scrubber that replaces common PII / secret patterns in
prompt content with stable opaque tokens (`<EMAIL_1>`, `<IPV4_1>`, …)
before the prompt leaves your process. A matching `rehydrate()` step
swaps the tokens back in the model's reply so end-users still see real
values.

Stdlib only. ~140 lines. No external regex packs, no ML.

## Why

Even an honest model provider logs prompts somewhere. Every credit
card, JWT, AWS key, or SSN you put in a prompt is now in someone
else's audit trail, plus any caching / fine-tune pipeline that runs
over that traffic. The cheap, boring fix is: don't send it in the
first place. Tokenize before, detokenize after.

This template is the minimum viable version: not a Presidio
replacement, but enough to defuse the obvious leaks and give you a
shape to extend.

## Detected entity types

| Label          | What it matches                                      | Notes |
|----------------|------------------------------------------------------|-------|
| `EMAIL`        | RFC-ish email                                        |       |
| `PHONE_US`     | 10-digit US phone, optional `+1` and separators      | Tightened by `(?<!\d) … (?!\d)` to avoid eating the middle of long numbers. |
| `IPV4`         | Dotted-quad with octet bound check                   |       |
| `SSN_US`       | `NNN-NN-NNNN`                                        |       |
| `CREDIT_CARD`  | 13–19 digit run, **Luhn-validated** before redacting | A 13-digit order id like `1234567890123` will NOT match. |
| `AWS_KEY_ID`   | `AKIA[A-Z0-9]{16}`                                   |       |
| `JWT`          | `eyJ…` 3-part base64url                              | Matched before `BEARER_TOKEN` (more specific). |
| `BEARER_TOKEN` | `Bearer <20+ url-safe chars>`                        |       |

Same value appearing twice in the input collapses to the **same**
token (so the model sees `<IPV4_1>` twice when the user wrote the
same IP twice — preserves co-reference).

## Files

| File | Purpose |
|---|---|
| `pii_redactor.py` | `redact(text) -> (scrubbed, mapping)` and `rehydrate(text, mapping) -> text`. |
| `worked_example.py` | A "draft a reply to this customer ticket" round-trip with realistic PII. Asserts that emails / cards / tokens are scrubbed, that a 13-digit order id is *not* mis-scrubbed as a card, and that rehydration restores the original strings. |

## Wire-up

```python
from pii_redactor import redact, rehydrate

scrubbed, mapping = redact(user_message)
reply = call_remote_model(scrubbed)        # remote provider only ever sees tokens
final = rehydrate(reply, mapping)          # local-only step
return final
```

Persist `mapping` ONLY in memory or in a store with the same trust
level as the original PII. The whole point is defeated if you log
mappings next to the scrubbed prompts.

## Worked example output

Run with:

```
python3 worked_example.py
```

Tail of actual output from the included run (the raw AWS key value is
elided here as `<aws-key-value>` so this README itself does not trip the
repo's pre-push secret guardrail; the live `worked_example.py` builds it
at runtime via string concatenation and the test asserts it is restored
losslessly):

```
=== SCRUBBED (this is what the model sees) ===
Hi support,

My name is Jordan Lee. My account email is <EMAIL_1> and my
backup email is <EMAIL_2>. You can also reach me at
<PHONE_US_1> or <PHONE_US_2>.

For verification: SSN <SSN_US_1>, last 4 of card <CREDIT_CARD_1>.
Our prod box is at <IPV4_1>; staging is <IPV4_1> (same machine).

I tried calling your API with header
  Authorization: <BEARER_TOKEN_1>
and also tested with AWS key <AWS_KEY_ID_1> — both returned 500.

Order #1234567890123 was placed yesterday. (Not a card number, just an order id.)

=== REHYDRATED REPLY (shown to human) ===
Hi Jordan,

Thanks for reaching out. We've logged the issue against your
account jordan.lee@example.com. We'll follow up by phone at +1 (415) 555-0142
within one business day.

Please rotate the credentials you shared (Bearer abcDEF1234567890ghIJKLmnOPqr
and <aws-key-value>) immediately — sharing them in a ticket
exposes them in our logs.

all invariants OK
```

Notes on what this proves:

* **Scrubbed text contains zero raw PII** — emails, phones, SSN,
  card, AWS key, bearer all replaced.
* **Co-reference preserved** — same IP appears as `<IPV4_1>` both
  times.
* **No false positive on order id** — `1234567890123` survives because
  Luhn check rejects it. Without Luhn, a naive 13-digit pattern would
  destroy this.
* **Rehydration is loss-free** — the human-facing reply has the
  user's real email and phone back in.

## Failure modes you should know about

* **Names, addresses, free-text PHI** — not detected. This template
  catches structured PII; for free-text personal names you need an
  NER model.
* **International phone numbers** — `PHONE_US` is US-only by design.
  Add a country-specific detector to `DETECTORS` if you need others.
* **Tokens in markdown / JSON** — the redactor is text-level. If the
  surrounding format is JSON, escape characters in the original may
  not survive a naive replace; rehydrate first, then re-encode.
* **Adversarial inputs** — a user can deliberately format a card
  number to evade the regex (e.g. `4111-1111  1111-1111` with extra
  spaces). The current regex tolerates `\s` and `-`; harden the
  pre-filter if your threat model includes that.

## Related templates

* `tool-output-redactor` — same shape applied to TOOL outputs before
  they re-enter the prompt.
* `agent-trace-redaction-rules` — coarser policy applied at trace
  storage time.
* `prompt-injection-boundary-tags` — orthogonal: marks where
  untrusted text begins/ends so the model doesn't treat scrubbed
  user content as instructions.
