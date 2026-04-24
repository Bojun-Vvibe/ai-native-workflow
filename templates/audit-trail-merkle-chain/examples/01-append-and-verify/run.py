"""Worked example 01: append four entries, verify, print head."""

from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "bin"))

from merkle_log import MerkleLog, verify  # noqa: E402


def main() -> int:
    log_path = os.path.join(HERE, "audit.jsonl")
    if os.path.exists(log_path):
        os.remove(log_path)

    ticks = iter([f"2026-04-24T10:00:{i:02d}Z" for i in range(20)])
    clock = lambda: next(ticks)  # noqa: E731

    log = MerkleLog(path=log_path, clock=clock)

    decisions = [
        {"actor": "agent-A", "action": "select_model", "value": "primary"},
        {"actor": "agent-A", "action": "tool_call", "value": "read_file:/spec.md"},
        {"actor": "agent-A", "action": "tool_call", "value": "write_file:/out.md"},
        {"actor": "agent-A", "action": "finish", "value": "ok"},
    ]

    for d in decisions:
        r = log.append(d)
        print(f"appended index={r.index} entry_hash={r.entry_hash[:16]}")

    head = log.head_hash()
    print(f"published_head={head[:16]}")

    result = verify(log_path, expected_head_hash=head)
    print(f"verify ok={result['ok']} entries={result['entries_verified']} head={result['head_hash'][:16]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
