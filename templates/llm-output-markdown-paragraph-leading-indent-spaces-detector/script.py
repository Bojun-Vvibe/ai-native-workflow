#!/usr/bin/env python3
"""Detect paragraph lines that start with 1-3 leading spaces.

In CommonMark, a paragraph line indented by 1-3 spaces is still a paragraph
(4+ spaces would make it an indented code block). LLMs sometimes emit such
lines unintentionally — for example, when wrapping prose around a list and
mistakenly indenting follow-on paragraphs to "align" them. The output
renders as a normal paragraph but the source is visually misleading and
breaks many linters.

This script reports every non-blank, non-list, non-fenced-code line that
begins with 1, 2, or 3 space characters and is the start of (or part of)
a paragraph block.

Reads stdin, writes findings to stdout, exits 1 on findings, 0 on clean input.
"""

from __future__ import annotations

import re
import sys

FENCE_RE = re.compile(r"^\s*(```|~~~)")
LIST_ITEM_RE = re.compile(r"^\s*([-*+]|\d+[.)])\s+")
HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s")
BLOCKQUOTE_RE = re.compile(r"^\s{0,3}>")
HR_RE = re.compile(r"^\s{0,3}([-*_])\s*(\1\s*){2,}$")
TABLE_RE = re.compile(r"^\s*\|")


def main() -> int:
    lines = sys.stdin.read().splitlines()

    in_fence = False
    findings: list[str] = []

    for idx, line in enumerate(lines, start=1):
        if FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if not line.strip():
            continue

        # Compute leading spaces (no tabs treated; tabs handled separately
        # by other detectors).
        stripped = line.lstrip(" ")
        leading = len(line) - len(stripped)
        if leading == 0 or leading >= 4:
            continue

        # Skip lines that are valid block constructs even when indented 1-3.
        if (
            LIST_ITEM_RE.match(line)
            or HEADING_RE.match(line)
            or BLOCKQUOTE_RE.match(line)
            or HR_RE.match(line)
            or TABLE_RE.match(line)
        ):
            continue
        # Skip setext underlines.
        if re.match(r"^\s{1,3}=+\s*$", line) or re.match(r"^\s{1,3}-+\s*$", line):
            continue

        preview = stripped[:40].rstrip()
        findings.append(
            f"line {idx}: paragraph starts with {leading} leading space(s): "
            f"{preview!r}"
        )

    if findings:
        for f in findings:
            print(f)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
