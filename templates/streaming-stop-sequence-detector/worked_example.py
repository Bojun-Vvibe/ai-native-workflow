"""Worked example: detect stop sequences across chunk boundaries."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from template import StopSequenceDetector  # noqa: E402


def run_case(label: str, stops, chunks):
    print(f"=== {label} ===")
    det = StopSequenceDetector(stops)
    emitted_parts = []
    hit = None
    for i, c in enumerate(chunks):
        emit, h = det.feed(c)
        emitted_parts.append(emit)
        print(f"  chunk[{i}]={c!r:40s} -> emit={emit!r:30s} hit={h}")
        if h is not None:
            hit = h
            break
    if hit is None:
        tail = det.flush()
        emitted_parts.append(tail)
        print(f"  flush -> {tail!r}")
    print(f"  total emitted: {''.join(emitted_parts)!r}")
    print(f"  hit: {hit}")
    print()


def main() -> int:
    # Case 1: stop straddles two chunks ("</st" | "op>")
    run_case(
        "boundary-spanning hit",
        stops=["</stop>"],
        chunks=["hello world </st", "op> trailing garbage"],
    )

    # Case 2: stop straddles three chunks
    run_case(
        "three-chunk straddle",
        stops=["\n\nUser:"],
        chunks=["answer is 42.", "\n\nUs", "er: next question"],
    )

    # Case 3: multiple competing stops, earliest wins
    run_case(
        "earliest of multiple stops",
        stops=["</stop>", "STOP"],
        chunks=["abc STOP def </stop> ghi"],
    )

    # Case 4: no hit at all -> flush returns the tail
    run_case(
        "no hit, flush tail",
        stops=["NEVER_APPEARS"],
        chunks=["alpha ", "beta ", "gamma"],
    )

    # Case 5: stop at very start of stream
    run_case(
        "stop at start",
        stops=["X"],
        chunks=["Xafter"],
    )

    # Programmatic assertions so failure is loud.
    det = StopSequenceDetector(["</stop>"])
    e1, h1 = det.feed("hello </st")
    e2, h2 = det.feed("op> tail")
    assert h1 is None, h1
    # hit index is relative to (leftover_buffer + new_chunk) at the feed call
    assert h2[0] == "</stop>" and h2[1] == 2, h2
    assert e1 + e2 == "hello ", (e1, e2)

    det2 = StopSequenceDetector(["ZZZ"])
    e, h = det2.feed("abc")
    # max_len-1 = 2 retained as buffer; only "a" is safe to emit
    assert h is None and e == "a", (e, h)
    assert det2.flush() == "bc"

    print("all assertions passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
