"""Worked example: 5 calls, 4 with various drift patterns + 1 clean retry.

Run with: python3 example.py
"""

from __future__ import annotations

from detector import Attempt, detect, fingerprint_attempt


def main() -> None:
    attempts = [
        # call 1: clean retry — args byte-identical across 3 attempts (the happy path).
        Attempt("call-001", 1, "http_get", {"url": "https://example.test/a", "timeout_s": 5}),
        Attempt("call-001", 2, "http_get", {"url": "https://example.test/a", "timeout_s": 5}),
        Attempt("call-001", 3, "http_get", {"url": "https://example.test/a", "timeout_s": 5}),

        # call 2: ghost edit — `content` mutated between attempt 1 and attempt 2.
        # The orchestrator's planner re-ran one step between throw-and-catch.
        Attempt("call-002", 1, "write_file", {"path": "/tmp/notes.md", "content": "draft v1"}),
        Attempt("call-002", 2, "write_file", {"path": "/tmp/notes.md", "content": "draft v2"}),

        # call 3: type drift — `amount` was int 100, retry sent float 100.0.
        # Same numeric value but the idempotency-key hash will diverge → double charge.
        Attempt("call-003", 1, "charge_card", {"card_id": "tok_abc", "amount": 100}),
        Attempt("call-003", 2, "charge_card", {"card_id": "tok_abc", "amount": 100.0}),

        # call 4: key added on retry — caller "helpfully" added a hint that wasn't there.
        Attempt("call-004", 1, "search_index", {"q": "kittens"}),
        Attempt("call-004", 2, "search_index", {"q": "kittens", "max_results": 10}),

        # call 5: tool name changed (caller's fallback ladder kicked in mid-call_id —
        # this is a *different* call wearing a stolen idempotency key, the most dangerous case).
        # Also: attempt_no jumps from 1 to 3 (no #2) → non-dense flag too.
        Attempt("call-005", 1, "embed_v1", {"text": "hello"}),
        Attempt("call-005", 3, "embed_v2", {"text": "hello"}),
    ]

    print("# Attempt fingerprints (same fingerprint within one call_id == clean retry)")
    for a in attempts:
        print(f"  {a.call_id} attempt={a.attempt_no} tool={a.tool:<12} fp={fingerprint_attempt(a)}")
    print()

    report = detect(attempts)
    print(f"# Drift report: calls_checked={report.calls_checked} attempts_checked={report.attempts_checked} ok={report.ok}")
    print(f"# Findings ({len(report.findings)}):")
    for f in report.findings:
        print(f"  [{f.call_id}] {f.kind}: {f.detail}")

    # Runtime invariants — these MUST hold or the README example is lying.
    assert report.calls_checked == 5
    assert report.attempts_checked == 11
    assert not report.ok
    kinds = sorted({f.kind for f in report.findings})
    assert kinds == ["key_added", "non_dense_attempt_no", "tool_changed", "type_changed", "value_changed"], kinds
    # call-001 has zero findings (the clean-retry happy path).
    assert not [f for f in report.findings if f.call_id == "call-001"]
    print("\n# All runtime invariants pass.")


if __name__ == "__main__":
    main()
