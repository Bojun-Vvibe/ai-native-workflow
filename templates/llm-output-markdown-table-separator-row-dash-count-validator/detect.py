#!/usr/bin/env python3
"""Detect markdown table separator rows whose dash-segment counts are
inconsistent in length (e.g. |---|--|------|).

A GitHub-flavored markdown table separator row looks like:

    | --- | :---: | ---: |

Each cell between pipes must be a run of dashes (optionally bookended
by a single ':' for alignment). Stylistic consistency wants all dash
runs in a single separator row to share the same dash count, because
LLMs commonly emit visually uneven separators that survive rendering
but read as sloppy diffs.

This detector flags any separator row whose non-empty dash segments
do not all have the same dash count. Cells with alignment colons are
counted by their internal dash run (so ':---:' has dash-count 3).

Code-fence aware: cells inside fenced code blocks are skipped.

Exit codes:
  0 = no findings
  1 = findings printed to stdout
  2 = usage error
"""
from __future__ import annotations

import re
import sys

FENCE_RE = re.compile(r"^\s*(```+|~~~+)")
# A separator-row cell: optional leading/trailing colon around >=3 dashes
CELL_RE = re.compile(r"^\s*:?-{2,}:?\s*$")


def is_separator_row(line: str) -> bool:
    s = line.strip()
    if not s.startswith("|") and "|" not in s:
        return False
    # Strip outer pipes if present
    inner = s.strip("|")
    if not inner:
        return False
    cells = inner.split("|")
    if len(cells) < 2:
        return False
    return all(CELL_RE.match(c) for c in cells)


def dash_count(cell: str) -> int:
    return cell.strip().strip(":").count("-")


def scan(text: str):
    in_fence = False
    findings = []
    for i, raw in enumerate(text.splitlines(), 1):
        if FENCE_RE.match(raw):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if not is_separator_row(raw):
            continue
        cells = [c for c in raw.strip().strip("|").split("|") if c.strip()]
        counts = [dash_count(c) for c in cells]
        if len(set(counts)) > 1:
            findings.append((i, counts, raw.rstrip("\n")))
    return findings


def main(argv):
    if len(argv) != 2:
        print("usage: detect.py <file.md>", file=sys.stderr)
        return 2
    with open(argv[1], "r", encoding="utf-8") as f:
        text = f.read()
    findings = scan(text)
    for line, counts, raw in findings:
        print(f"{argv[1]}:{line}: separator-row dash counts {counts}: {raw}")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
