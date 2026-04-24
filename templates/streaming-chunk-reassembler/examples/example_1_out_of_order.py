"""Example 1: out-of-order delivery with one duplicate.

Producer sends 5 chunks in seq order, transport reorders them and
duplicates one. Reassembler still produces the original ordered stream
exactly once.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from reassembler import StreamReassembler


def main() -> int:
    # Original producer order: ["The ", "quick ", "brown ", "fox.", ""]
    # The empty final chunk carries is_final=True (common pattern).
    chunks = [
        {"seq": 0, "data": "The ",    "is_final": False},
        {"seq": 1, "data": "quick ",  "is_final": False},
        {"seq": 2, "data": "brown ",  "is_final": False},
        {"seq": 3, "data": "fox.",    "is_final": False},
        {"seq": 4, "data": "",        "is_final": True},
    ]
    # Deterministic out-of-order arrival, with seq=2 duplicated.
    arrival_order = [0, 2, 4, 1, 2, 3]

    r = StreamReassembler()
    delivered_seqs: list[int] = []
    output_text_parts: list[str] = []

    for arrival_idx in arrival_order:
        ch = chunks[arrival_idx]
        new = r.accept(ch)
        for d in new:
            delivered_seqs.append(d["seq"])
            output_text_parts.append(d["data"])
        print(
            f"arrival seq={ch['seq']:>1} -> delivered_now="
            f"{[d['seq'] for d in new]} state={json.dumps(r.state(), sort_keys=True)}"
        )

    print()
    print(f"final delivered seq order: {delivered_seqs}")
    print(f"reassembled text: {''.join(output_text_parts)!r}")
    print(f"is_complete: {r.is_complete()}")
    print(f"total chunks delivered: {r.state()['delivered_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
