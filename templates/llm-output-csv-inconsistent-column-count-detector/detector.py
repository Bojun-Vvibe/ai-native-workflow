#!/usr/bin/env python3
"""Detect rows in CSV output whose column count differs from the header.

LLMs frequently emit CSV with drifting column counts:
    - extra trailing comma → row has +1 column
    - missing field → row has -1 column
    - unescaped comma inside an unquoted free-text cell → row has +N columns

This detector uses Python's stdlib `csv` module to parse with the standard
dialect, then reports any row whose field count != header field count.

Usage:
    python3 detector.py < input.csv

Reads CSV from stdin. The first non-empty line is treated as the header.
Prints one finding per offending row:

    row=<N> expected=<H> actual=<A> first_field=<repr>

Exit code: 0 always (advisory).
"""
from __future__ import annotations

import csv
import io
import sys


def main() -> int:
    data = sys.stdin.read()
    if not data.strip():
        print("total_findings=0", file=sys.stderr)
        return 0

    reader = csv.reader(io.StringIO(data))
    header: list[str] | None = None
    findings: list[tuple[int, int, int, str]] = []
    expected_cols = 0

    for row_idx, row in enumerate(reader, start=1):
        if header is None:
            # Skip leading totally-empty rows.
            if not row or (len(row) == 1 and row[0] == ""):
                continue
            header = row
            expected_cols = len(header)
            continue
        # Skip empty rows (just trailing newlines).
        if not row or (len(row) == 1 and row[0] == ""):
            continue
        if len(row) != expected_cols:
            first = row[0] if row else ""
            findings.append((row_idx, expected_cols, len(row), first))

    for rn, exp, act, first in findings:
        print(f"row={rn} expected={exp} actual={act} first_field={first!r}")
    print(f"total_findings={len(findings)}", file=sys.stderr)
    if header is not None:
        print(f"header_columns={expected_cols}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
