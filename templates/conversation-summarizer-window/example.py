#!/usr/bin/env python3
"""End-to-end worked example for conversation-summarizer-window.

Builds a 6-message conversation that crosses the trigger threshold,
compresses it, then continues adding turns and shows the second
compression cycle (where the synthetic summary itself eventually gets
folded into a NEW summary).
"""

from __future__ import annotations

import json

from summarizer import (
    Message,
    SummarizerWindow,
    default_token_counter,
)


def fake_summarizer(msgs):
    """Stand-in for an LLM summarizer. Real callers inject a real one.

    For the worked example we use a deterministic stub so the README
    output is reproducible.
    """
    bullets = []
    for m in msgs:
        snippet = m.content[:30].replace("\n", " ")
        bullets.append(f"- {m.role} ({m.msg_id}): {snippet}...")
    body = "\n".join(bullets)
    return f"[summary covering {len(msgs)} messages]\n{body}"


def dump(label, msgs):
    print(f"--- {label} ---")
    for m in msgs:
        print(json.dumps({
            "role": m.role,
            "msg_id": m.msg_id,
            "pinned": m.pinned,
            "tokens": default_token_counter(m.content),
        }, sort_keys=True))
    total = sum(default_token_counter(m.content) for m in msgs)
    print(f"total_tokens={total}")
    print()


def main() -> int:
    sw = SummarizerWindow(
        window_tokens=400,
        trigger_pct=0.80,        # compress at >= 320 tokens
        target_pct=0.50,         # compress down to <= 200 tokens
        summarize_fn=fake_summarizer,
    )

    msgs = [
        Message("system", "You are a careful assistant. " * 5, pinned=True, msg_id="sys"),
        Message("user", "Q1: " + "alpha " * 50, msg_id="u1"),
        Message("assistant", "A1: " + "beta " * 50, msg_id="a1"),
        Message("user", "Q2: " + "gamma " * 50, msg_id="u2"),
        Message("assistant", "A2: " + "delta " * 50, msg_id="a2"),
        Message("user", "Q3 (latest, short): summarise", msg_id="u3"),
    ]

    dump("initial conversation", msgs)
    print(json.dumps({
        "should_compress": sw.should_compress(msgs),
        "trigger_threshold": int(sw.window_tokens * sw.trigger_pct),
    }, sort_keys=True))
    print()

    msgs, report = sw.compress(msgs)
    print("--- compression report (round 1) ---")
    print(json.dumps(report, sort_keys=True, indent=2))
    print()
    dump("after compression (round 1)", msgs)

    # Verify pinned system prompt survived
    pinned_survived = any(m.pinned and m.msg_id == "sys" for m in msgs)
    has_summary = any(m.role == "summary" for m in msgs)
    assert pinned_survived, "pinned system prompt was dropped!"
    assert has_summary, "no summary message inserted!"

    # Now add more turns until we re-trigger.
    msgs.append(Message("assistant", "A3: " + "epsilon " * 60, msg_id="a3"))
    msgs.append(Message("user", "Q4: " + "zeta " * 60, msg_id="u4"))
    msgs.append(Message("assistant", "A4: " + "eta " * 60, msg_id="a4"))

    dump("after 3 more turns", msgs)
    print(json.dumps({"should_compress": sw.should_compress(msgs)}, sort_keys=True))
    print()

    msgs, report = sw.compress(msgs)
    print("--- compression report (round 2) ---")
    print(json.dumps(report, sort_keys=True, indent=2))
    print()
    dump("after compression (round 2)", msgs)

    # Final invariants check
    final_total = sum(default_token_counter(m.content) for m in msgs)
    pinned_still_first_nonsummary = msgs[0].pinned and msgs[0].msg_id == "sys"
    print(json.dumps({
        "final_total_tokens": final_total,
        "under_window": final_total <= sw.window_tokens,
        "pinned_still_at_top": pinned_still_first_nonsummary,
    }, sort_keys=True, indent=2))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
