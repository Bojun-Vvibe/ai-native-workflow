"""Worked example for prompt-message-role-sequence-validator.

Five scenarios covering the common failure modes:
  S1 clean 5-turn conversation with one tool round-trip — PASS
  S2 missing system + duplicate system later
  S3 consecutive assistant turns + empty assistant turn
  S4 tool message with no matching assistant tool_calls
  S5 assistant declares tool_calls then another assistant arrives without reply
     (covers both `unanswered_tool_call` and `consecutive_assistant`)
"""

from __future__ import annotations

import json

from validator import validate


def banner(title: str) -> None:
    print()
    print("=" * 72)
    print(title)
    print("=" * 72)


def show(name: str, messages: list[dict]) -> None:
    banner(name)
    print("messages:")
    for i, m in enumerate(messages):
        compact = {k: v for k, v in m.items() if k != "content"}
        content = m.get("content")
        if isinstance(content, str):
            preview = content if len(content) <= 40 else content[:37] + "..."
            compact["content"] = preview
        elif content is None:
            compact["content"] = None
        print(f"  [{i}] {compact}")
    result = validate(messages)
    print("\nresult:")
    print(json.dumps(result.to_dict(), indent=2, sort_keys=True))


# ---------------------------------------------------------------------------
# S1: clean conversation
# ---------------------------------------------------------------------------
S1 = [
    {"role": "system", "content": "You answer in one sentence."},
    {"role": "user", "content": "What is 2+2?"},
    {
        "role": "assistant",
        "content": None,
        "tool_calls": [{"id": "call_1", "name": "calc", "args": {"expr": "2+2"}}],
    },
    {"role": "tool", "tool_call_id": "call_1", "content": "4"},
    {"role": "assistant", "content": "It is 4."},
]

# ---------------------------------------------------------------------------
# S2: no system at start, then a system later
# ---------------------------------------------------------------------------
S2 = [
    {"role": "user", "content": "hi"},
    {"role": "assistant", "content": "hello"},
    {"role": "system", "content": "by the way, be terse"},
    {"role": "user", "content": "ok"},
]

# ---------------------------------------------------------------------------
# S3: consecutive assistant + empty no-op assistant
# ---------------------------------------------------------------------------
S3 = [
    {"role": "system", "content": "be helpful"},
    {"role": "user", "content": "hi"},
    {"role": "assistant", "content": "first half"},
    {"role": "assistant", "content": "   "},  # empty + consecutive
]

# ---------------------------------------------------------------------------
# S4: tool message with no matching assistant tool_calls
# ---------------------------------------------------------------------------
S4 = [
    {"role": "system", "content": "be helpful"},
    {"role": "user", "content": "tell me the time"},
    {"role": "assistant", "content": "let me check"},
    {"role": "tool", "tool_call_id": "call_xyz", "content": "12:00"},
    {"role": "assistant", "content": "noon"},
]

# ---------------------------------------------------------------------------
# S5: assistant declares tool_calls but another assistant takes over
# ---------------------------------------------------------------------------
S5 = [
    {"role": "system", "content": "be helpful"},
    {"role": "user", "content": "lookup user 42"},
    {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {"id": "call_a", "name": "db_get", "args": {"id": 42}},
            {"id": "call_b", "name": "audit_log", "args": {"id": 42}},
        ],
    },
    {"role": "assistant", "content": "user 42 is bob"},
]


def main() -> None:
    show("S1 — clean tool round-trip (expected: PASS)", S1)
    show("S2 — missing system + duplicate system (expected: FAIL)", S2)
    show("S3 — consecutive assistant + empty assistant (expected: FAIL)", S3)
    show("S4 — tool message with no matching call (expected: FAIL)", S4)
    show("S5 — declared tool_calls left unanswered (expected: FAIL)", S5)


if __name__ == "__main__":
    main()
