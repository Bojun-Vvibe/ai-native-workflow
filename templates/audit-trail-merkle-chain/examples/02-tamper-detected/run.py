"""Worked example 02: tamper with one byte mid-chain, verify breaks at exact index."""

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

    ticks = iter([f"2026-04-24T11:00:{i:02d}Z" for i in range(20)])
    clock = lambda: next(ticks)  # noqa: E731

    log = MerkleLog(path=log_path, clock=clock)
    for i, action in enumerate(["plan", "draft", "review", "approve", "ship"]):
        log.append({"step": i, "action": action})

    head_before = log.head_hash()
    pre = verify(log_path, expected_head_hash=head_before)
    print(f"clean ok={pre['ok']} entries={pre['entries_verified']} head={pre['head_hash'][:16]}")

    # Tamper: rewrite line at index 2, replacing "review" with "rEview".
    with open(log_path, "r", encoding="utf-8") as fh:
        lines = fh.readlines()
    lines[2] = lines[2].replace("review", "rEview")
    with open(log_path, "w", encoding="utf-8") as fh:
        fh.writelines(lines)
    print("tampered: replaced 'review' with 'rEview' at line index 2")

    post = verify(log_path, expected_head_hash=head_before)
    print(
        f"tampered ok={post['ok']} broken_at_index={post.get('broken_at_index')} "
        f"reason={post.get('reason')}"
    )
    return 0 if not post["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
