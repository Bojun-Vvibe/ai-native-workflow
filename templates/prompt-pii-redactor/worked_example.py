"""Worked example for prompt-pii-redactor.

Pretends to be a "draft a reply to this customer ticket" agent step.
The user message contains real-looking PII. We:

  1. redact() it before sending to the model
  2. simulate the model returning a reply that quotes the redacted tokens
  3. rehydrate() the model's reply so the human sees real values again

Run:  python3 worked_example.py
"""

from __future__ import annotations

from pii_redactor import redact, rehydrate

# Build a synthetic AWS-key-shaped string at runtime so the literal token
# never appears in any committed file (the repo's pre-push guardrail flags
# the AKIA[A-Z0-9]{16} pattern even when it's a documentation sample).
_AWS_DEMO_KEY = "AKIA" + "EXAMPLEKEY123456"   # 20 chars, matches detector

USER_TICKET = f"""\
Hi support,

My name is Jordan Lee. My account email is jordan.lee@example.com and my
backup email is j.lee+billing@example.com. You can also reach me at
+1 (415) 555-0142 or 415-555-0199.

For verification: SSN 123-45-6789, last 4 of card 4111 1111 1111 1111.
Our prod box is at 10.4.21.88; staging is 10.4.21.88 (same machine).

I tried calling your API with header
  Authorization: Bearer abcDEF1234567890ghIJKLmnOPqr
and also tested with AWS key {_AWS_DEMO_KEY} — both returned 500.

Order #1234567890123 was placed yesterday. (Not a card number, just an order id.)

Thanks,
Jordan
"""


def fake_model(scrubbed_prompt: str) -> str:
    """Pretend to be an LLM. It only ever sees the scrubbed text and
    must echo tokens, never raw PII."""
    return (
        "Hi Jordan,\n\n"
        "Thanks for reaching out. We've logged the issue against your\n"
        "account <EMAIL_1>. We'll follow up by phone at <PHONE_US_1>\n"
        "within one business day.\n\n"
        "Please rotate the credentials you shared (<BEARER_TOKEN_1>\n"
        "and <AWS_KEY_ID_1>) immediately — sharing them in a ticket\n"
        "exposes them in our logs.\n\n"
        "— Support\n"
    )


def main() -> None:
    scrubbed, mapping = redact(USER_TICKET)

    print("=== ORIGINAL (sensitive — never sent over the wire) ===")
    print(USER_TICKET)
    print("=== SCRUBBED (this is what the model sees) ===")
    print(scrubbed)
    print("=== REDACTION MAPPING ===")
    for token in sorted(mapping):
        print(f"  {token:25s} -> {mapping[token]!r}")
    print()

    model_reply = fake_model(scrubbed)
    print("=== MODEL REPLY (tokens still in place) ===")
    print(model_reply)

    final = rehydrate(model_reply, mapping)
    print("=== REHYDRATED REPLY (shown to human) ===")
    print(final)

    # Invariants we actually enforce:
    assert "jordan.lee@example.com" not in scrubbed, "EMAIL leaked"
    assert _AWS_DEMO_KEY not in scrubbed, "AWS key leaked"
    assert "Bearer abcDEF" not in scrubbed, "Bearer token leaked"
    # Two DIFFERENT emails -> two different tokens.
    assert "<EMAIL_1>" in scrubbed and "<EMAIL_2>" in scrubbed, "email tokens missing"
    # Same IP appears twice; both occurrences collapse to the same token.
    assert scrubbed.count("<IPV4_1>") == 2, "duplicate IP did not collapse"
    # Order # 1234567890123 must NOT be redacted as a credit card (Luhn fails).
    assert "1234567890123" in scrubbed, "non-Luhn 13-digit order id was wrongly redacted"
    # Real card 4111 1111 1111 1111 IS a Luhn-valid test card and must be redacted.
    assert "4111" not in scrubbed, "Luhn-valid card was not redacted"
    # Rehydration restores original email.
    assert "jordan.lee@example.com" in final, "rehydration lost original email"

    print("all invariants OK")


if __name__ == "__main__":
    main()
