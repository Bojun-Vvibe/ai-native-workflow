"""Worked example: simulate a streaming model that emits a structured
plan one chunk at a time. After every chunk we render the partial
view. The caller sees the `plan` array fill up before `answer` arrives.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from streaming_parser import StreamingJSONParser  # noqa: E402


# A realistic streaming sequence: a model emits this object in
# odd-shaped chunks (mid-string, mid-number, mid-escape).
FULL = (
    '{"plan": ['
    '{"step": 1, "action": "read README.md"},'
    '{"step": 2, "action": "list templates dir"},'
    '{"step": 3, "action": "pick two angles"}'
    '], "confidence": 0.87, "answer": "proceed with arbiter + parser"}'
)

# Deliberately ugly chunk boundaries to stress the parser.
CHUNKS = [
    '{"plan": [',
    '{"step": 1, "action": "read READ',
    'ME.md"},',
    '{"step": 2, "ac',
    'tion": "list templates dir"},',
    '{"step": 3, "action": "pick two angles"}',
    '], "confidence": 0.',
    "87",
    ', "answer": "proceed with arbi',
    'ter + parser"}',
]


def main() -> None:
    parser = StreamingJSONParser()
    print(f"# streaming-json-parser demo  ({len(CHUNKS)} chunks)")
    print()
    for i, chunk in enumerate(CHUNKS, start=1):
        parser.feed(chunk)
        snap = parser.snapshot()
        plan_len = len(snap.get("plan", [])) if isinstance(snap, dict) else 0
        has_answer = isinstance(snap, dict) and "answer" in snap
        print(
            f"chunk {i:2d}  bytes_in={len(chunk):>3}  "
            f"complete={parser.complete}  "
            f"plan_steps={plan_len}  has_answer={has_answer}"
        )
        # Show the snapshot on a few representative iterations.
        if i in (1, 3, 6, 8, len(CHUNKS)):
            print(f"          snapshot: {json.dumps(snap, sort_keys=True)}")

    print()
    final = parser.snapshot()
    expected = json.loads(FULL)
    print(f"final snapshot equals fully-buffered parse?  {final == expected}")
    print(f"final snapshot: {json.dumps(final, indent=2, sort_keys=True)}")


if __name__ == "__main__":
    main()
