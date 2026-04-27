#!/usr/bin/env python3
"""Validate that every ATX heading is preceded by a blank line.

CommonMark renders ATX headings correctly even when no blank line
precedes them, but most style guides (and `markdownlint` rule MD022)
require a blank line above each heading for readability and to avoid
edge-case render bugs in some renderers.

LLMs commonly emit headings flush against the preceding paragraph
when streaming output, especially after lists or code blocks. The
render usually still works but the source is ugly and inconsistent.

This script flags every ATX heading (other than the first non-blank
line of the document) whose immediately preceding line is non-blank.
Fenced code blocks are skipped, as are headings inside them.

Exits 1 on findings, 0 on clean input.
"""

from __future__ import annotations

import re
import sys

FENCE_RE = re.compile(r"^\s*(```|~~~)")
ATX_RE = re.compile(r"^\s{0,3}#{1,6}(\s|$)")


def main() -> int:
    lines = sys.stdin.read().splitlines()

    in_fence = False
    findings: list[str] = []
    seen_first_nonblank = False

    for idx, line in enumerate(lines, start=1):
        if FENCE_RE.match(line):
            in_fence = not in_fence
            seen_first_nonblank = True
            continue
        if in_fence:
            continue

        is_blank = not line.strip()
        if is_blank:
            continue

        # Skip indented code blocks.
        if line.startswith("    "):
            seen_first_nonblank = True
            continue

        if ATX_RE.match(line):
            if not seen_first_nonblank:
                # First non-blank line of the document; no blank line required.
                seen_first_nonblank = True
                continue
            prev = lines[idx - 2] if idx >= 2 else ""
            if prev.strip():
                preview = line.strip()[:50]
                findings.append(
                    f"line {idx}: heading not preceded by blank line: {preview!r}"
                )

        seen_first_nonblank = True

    if findings:
        for f in findings:
            print(f)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
