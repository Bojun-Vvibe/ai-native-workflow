"""Worked example: replay a streamed tool-call session.

Simulates the kind of SSE delta sequence a host receives from a
streaming chat completion that decides to call two tools (one of which
arrives in fragments and finishes mid-stream, the other of which is
malformed and must be quarantined, plus a finalize-only zero-arg call).

Run:  python3 run.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Make the parent template package importable.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from buffer import (  # noqa: E402
    CompletedCall,
    MalformedCall,
    StreamingToolCallBuffer,
)


# Each entry is one SSE delta the host would receive.
DELTAS = [
    # Call 0: search_repo — arguments arrive in 5 fragments.
    {"index": 0, "id": "call_a1", "name": "search_repo"},
    {"index": 0, "arguments": '{"query": "ret'},
    {"index": 0, "arguments": "ry budget"},
    {"index": 0, "arguments": '", "limit":'},
    {"index": 0, "arguments": " 5"},
    {"index": 0, "arguments": "}"},
    # Stream advances to call 1 -> call 0 implicitly completes.
    {"index": 1, "id": "call_b2", "name": "open_file"},
    {"index": 1, "arguments": '{"path": "src/agent.py", "line"'},
    {"index": 1, "arguments": ': 42'},  # missing closing brace ...
    {"index": 1, "arguments": ", oops"},  # ... and now invalid JSON
    {"index": 1, "finalize": True},
    # Call 2: zero-arg tool, only a finalize signal.
    {"index": 2, "id": "call_c3", "name": "list_open_prs", "finalize": True},
]


def main() -> int:
    completed: list[CompletedCall] = []
    malformed: list[MalformedCall] = []

    buf = StreamingToolCallBuffer(
        on_complete=completed.append,
        on_malformed=malformed.append,
    )
    for d in DELTAS:
        buf.feed(d)
    buf.finish()

    print("=== Completed calls ===")
    for c in completed:
        print(
            f"  [#{c.index}] {c.name}({json.dumps(c.arguments, sort_keys=True)})"
            f"  id={c.call_id}"
        )
    print()
    print("=== Quarantined (malformed) calls ===")
    for m in malformed:
        print(f"  [#{m.index}] {m.name} -> {m.error}")
        print(f"     raw: {m.raw_arguments!r}")
    print()
    print(
        f"summary: {len(completed)} dispatched, "
        f"{len(malformed)} quarantined, "
        f"{len(DELTAS)} deltas consumed"
    )

    # Self-check so the example fails loudly if the buffer regresses.
    assert len(completed) == 2, completed
    assert len(malformed) == 1, malformed
    assert completed[0].arguments == {"query": "retry budget", "limit": 5}
    assert completed[1].name == "list_open_prs"
    assert completed[1].arguments == {}
    assert malformed[0].index == 1
    print("self-check: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
