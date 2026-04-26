#!/usr/bin/env python3
"""Detect inconsistent ellipsis styles in LLM output.

Flags every ellipsis occurrence and reports the dominant style plus
each deviation. Recognized styles:
  - "unicode"      : the single character "\u2026"
  - "three_dots"   : exactly three ASCII dots "..."
  - "spaced_dots"  : ". . ." (spaced)
  - "long_dots"    : four or more consecutive ASCII dots

Stdlib only. Reads from a file path argv[1] or from STDIN.
Exit code: 0 if a single style is used (or no ellipses), 1 otherwise.
"""
from __future__ import annotations

import re
import sys
from collections import Counter


PATTERNS = [
    ("unicode", re.compile(r"\u2026")),
    ("spaced_dots", re.compile(r"\.\s\.\s\.")),
    ("long_dots", re.compile(r"\.{4,}")),
    ("three_dots", re.compile(r"(?<!\.)\.{3}(?!\.)")),
]


def find_occurrences(text: str):
    hits = []
    for style, pat in PATTERNS:
        for m in pat.finditer(text):
            hits.append((m.start(), style, m.group(0)))
    hits.sort(key=lambda t: t[0])
    return hits


def line_col(text: str, offset: int):
    line = text.count("\n", 0, offset) + 1
    last_nl = text.rfind("\n", 0, offset)
    col = offset - last_nl
    return line, col


def report(text: str) -> int:
    hits = find_occurrences(text)
    if not hits:
        print("OK: no ellipses found")
        return 0
    counts = Counter(style for _, style, _ in hits)
    print(f"Found {len(hits)} ellipsis occurrence(s) across {len(counts)} style(s):")
    for style, n in counts.most_common():
        print(f"  - {style}: {n}")
    if len(counts) == 1:
        print("OK: consistent style")
        return 0
    dominant = counts.most_common(1)[0][0]
    print(f"\nDominant style: {dominant}")
    print("Deviations:")
    for offset, style, snippet in hits:
        if style == dominant:
            continue
        ln, col = line_col(text, offset)
        print(f"  line {ln} col {col}: {style!r} -> {snippet!r}")
    return 1


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] != "-":
        with open(sys.argv[1], "r", encoding="utf-8") as fh:
            text = fh.read()
    else:
        text = sys.stdin.read()
    return report(text)


if __name__ == "__main__":
    sys.exit(main())
