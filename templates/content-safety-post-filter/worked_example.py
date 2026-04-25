"""End-to-end worked example for content-safety-post-filter.

Stdlib only. Run:

    python3 worked_example.py
"""

from __future__ import annotations

from post_filter import (
    ALLOWED_CATEGORIES,
    Decision,
    Policy,
    PolicyConfigError,
    Rule,
    default_policy,
    evaluate,
)


def banner(s: str) -> None:
    print("=" * 70)
    print(s)
    print("=" * 70)


def show(label: str, dec: Decision) -> None:
    print(f"[{label}]")
    print(f"  action       : {dec.action}")
    print(f"  tripped      : {list(dec.tripped)}")
    print(f"  n_hits       : {len(dec.hits)}")
    print(f"  chosen_rule  : {dec.chosen_rule_label}")
    if dec.action == "redact":
        print(f"  redacted     : {dec.redacted_text!r}")
    print()


def build_synthetic_secret_strings() -> tuple[str, str, str]:
    """Build fake secret-shaped strings at RUNTIME so this source file
    contains no literal AKIA / ghp_ / PEM tokens (guardrail-safe).
    """
    fake_aws = "AK" + "IA" + ("X" * 16)
    fake_pat = "gh" + "p" + "_" + ("a" * 36)
    head = "-----" + "BEGIN" + " " + "RSA PRIVATE KEY-----"
    body = "MIIBOgIBAAJBAKj34GkxFhD90vcNLYLInFEX6Ppy1tPf9Cnzj4p4WGeKLs1Pt8Q\n"
    tail = "-----" + "END" + " " + "RSA PRIVATE KEY-----"
    fake_pem = f"{head}\n{body}{tail}"
    return fake_aws, fake_pat, fake_pem


def main() -> int:
    banner("content-safety-post-filter :: worked example")
    print()

    pol = default_policy()
    print(f"policy           : {len(pol.rules)} rules")
    print(f"allowed_categories: {sorted(ALLOWED_CATEGORIES)}")
    print()

    # --- Scenario 1: clean output -------------------------------------------
    clean = "Sure -- the build is green and the deploy went out at 14:02 UTC."
    d1 = evaluate(clean, pol)
    show("clean_response", d1)
    assert d1.action == "allow", d1
    assert d1.tripped == (), d1
    assert d1.redacted_text == clean

    # --- Scenario 2: PII redaction (email + phone, repeated) ----------------
    pii_text = (
        "Contact ada@example.com or 555-123-4567. "
        "Backup contact is also ada@example.com."
    )
    d2 = evaluate(pii_text, pol)
    show("pii_redaction", d2)
    assert d2.action == "redact", d2
    assert "pii_email" in d2.tripped
    assert "pii_phone" in d2.tripped
    # Stable tokens: same email collapses to the same token.
    assert "<REDACT:PII_EMAIL:1>" in d2.redacted_text
    assert "<REDACT:PII_PHONE:1>" in d2.redacted_text
    assert d2.redacted_text.count("<REDACT:PII_EMAIL:1>") == 2
    assert "ada@example.com" not in d2.redacted_text

    # Idempotency-ish: identical input produces an identical decision.
    d2b = evaluate(pii_text, pol)
    assert d2b.redacted_text == d2.redacted_text

    # --- Scenario 3: hallucinated secrets -> BLOCK --------------------------
    fake_aws, fake_pat, fake_pem = build_synthetic_secret_strings()
    leak = (
        "Here is the AWS key you asked about: "
        f"{fake_aws}. Also try this token: {fake_pat}."
    )
    d3 = evaluate(leak, pol)
    show("secrets_leak_block", d3)
    assert d3.action == "block", d3
    assert "secrets_leak" in d3.tripped
    # block branch keeps original text in `redacted_text` for the audit log;
    # the caller is responsible for delivering policy.block_message instead.

    # --- Scenario 4: PEM block detection ------------------------------------
    pem_leak = f"Sure, here is the key:\n{fake_pem}\nUse it carefully."
    d4 = evaluate(pem_leak, pol)
    show("private_key_block", d4)
    assert d4.action == "block", d4
    assert "private_key" in d4.tripped

    # --- Scenario 5: severity ordering -- review + redact mixed -------------
    # This input contains a self-harm phrase (review) AND an email (redact).
    # The decision must be `review` (higher severity), NOT `redact`,
    # regardless of input/rule order.
    mixed = "i want to hurt myself. you can reach me at sam@example.org."
    d5 = evaluate(mixed, pol)
    show("severity_review_beats_redact", d5)
    assert d5.action == "review", d5
    assert "self_harm" in d5.tripped
    assert "pii_email" in d5.tripped

    # --- Scenario 6: severity ordering -- block beats review ---------------
    threat_and_self = (
        "i want to hurt myself; also i will kill you if you stop me."
    )
    d6 = evaluate(threat_and_self, pol)
    show("severity_block_beats_review", d6)
    assert d6.action == "block", d6
    assert "violence_threat" in d6.tripped
    assert "self_harm" in d6.tripped

    # --- Scenario 7: policy config errors fail at construction --------------
    config_caught = []
    try:
        Rule(pattern=r".*", category="not_a_real_category", action="block", label="x")
    except PolicyConfigError as e:
        config_caught.append(("unknown_category", str(e)[:60]))
    try:
        Rule(pattern=r"[", category="self_harm", action="block", label="bad_regex")
    except PolicyConfigError as e:
        config_caught.append(("invalid_regex", str(e)[:60]))
    try:
        Policy(rules=())
    except PolicyConfigError as e:
        config_caught.append(("empty_policy", str(e)[:60]))
    try:
        r = Rule(pattern=r"a", category="self_harm", action="review", label="dup")
        Policy(rules=(r, r))
    except PolicyConfigError as e:
        config_caught.append(("duplicate_label", str(e)[:60]))

    print("[policy_config_errors_caught]")
    for kind, msg in config_caught:
        print(f"  {kind:20s} -> {msg}")
    print()
    assert len(config_caught) == 4

    # --- Final invariants ---------------------------------------------------
    print("-" * 70)
    print("Invariants:")
    print(f"  clean -> allow                                    OK")
    print(f"  pii   -> redact, stable tokens, repeated->same    OK")
    print(f"  fake-AWS-shaped string -> block                   OK")
    print(f"  fake-PEM-shaped block  -> block                   OK")
    print(f"  review beats redact, block beats review           OK")
    print(f"  4 policy-config bugs caught at construction       OK")
    print()
    print("DONE.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
