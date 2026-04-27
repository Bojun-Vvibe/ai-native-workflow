#!/usr/bin/env python3
"""Detect runs of two or more consecutive blank lines outside fenced code.

CommonMark collapses any run of consecutive blank lines into a single
paragraph break, so multiple blank lines in source are visually noisy and
have no semantic meaning. LLMs frequently emit doubled or tripled blank
lines when concatenating sections — especially around headings, lists, or
code blocks — which makes diffs noisier and triggers markdownlint MD012.

This script reports every run of >=2 consecutive blank lines that occurs
outside a fenced code block. A "blank" line is one that is empty or
contains only whitespace.

Reads stdin, writes findings to stdout, exits 1 on findings, 0 on clean
input.
"""

from __future__ import annotations

import re
import sys

FENCE_RE = re.compile(r"^\s*(```|~~~)")


def main() -> int:
    lines = sys.stdin.read().splitlines()

    in_fence = False
    findings: list[str] = []

    run_start: int | None = None
    run_len = 0

    def flush(end_line: int) -> None:
        nonlocal run_start, run_len
        if run_start is not None and run_len >= 2:
            findings.append(
                f"lines {run_start}-{end_line}: {run_len} consecutive "
                f"blank lines (collapse to 1)"
            )
        run_start = None
        run_len = 0

    for idx, line in enumerate(lines, start=1):
        if FENCE_RE.match(line):
            # Fence boundary terminates any blank-line run we were tracking
            # (the fence line itself is non-blank).
            flush(idx - 1)
            in_fence = not in_fence
            continue
        if in_fence:
            # Blank lines inside fenced code are part of the code block and
            # carry meaning; do not flag.
            flush(idx - 1)
            continue

        if line.strip() == "":
            if run_start is None:
                run_start = idx
                run_len = 1
            else:
                run_len += 1
        else:
            flush(idx - 1)

    # Flush trailing run at end-of-file.
    flush(len(lines))

    if findings:
        for f in findings:
            print(f)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
