#!/usr/bin/env python3
"""Detect inconsistent ATX heading trailing-hash style within a document.

CommonMark allows two ATX heading forms:

  ## Foo            (open style, no trailing hashes)
  ## Foo ##         (closed style, optional trailing hashes)

Both render identically. LLMs sometimes mix the two styles within the same
document — for example, opening with `# Title` then later emitting
`## Section ##`. The rendered output is fine but the source is inconsistent
and many style guides require one form throughout.

This script reads stdin, picks the dominant style (whichever appears
first), and flags every ATX heading using the other style. Fenced code
blocks and indented code blocks are skipped.

Exits 1 on findings, 0 on clean input.
"""

from __future__ import annotations

import re
import sys

FENCE_RE = re.compile(r"^\s*(```|~~~)")
# ATX heading: 1-6 #, then space, then content. Trailing hashes (if any)
# must be preceded by a space and may be followed only by trailing spaces.
ATX_RE = re.compile(r"^\s{0,3}(#{1,6})\s+(.*?)\s*$")
TRAILING_HASH_RE = re.compile(r"^(.*?)\s+#+\s*$")


def classify(line: str) -> str | None:
    """Return 'closed' if line ends with trailing hashes, 'open' otherwise.

    Returns None if line is not an ATX heading.
    """
    m = ATX_RE.match(line)
    if not m:
        return None
    content = m.group(2)
    if not content:
        # Empty heading like "## " — treat as open.
        return "open"
    # A trailing-hash sequence must be preceded by a space.
    if TRAILING_HASH_RE.match(content):
        return "closed"
    return "open"


def main() -> int:
    lines = sys.stdin.read().splitlines()

    in_fence = False
    headings: list[tuple[int, str, str]] = []  # (lineno, style, raw)

    for idx, line in enumerate(lines, start=1):
        if FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        # Skip indented code blocks (4+ leading spaces).
        if line.startswith("    "):
            continue
        style = classify(line)
        if style is None:
            continue
        headings.append((idx, style, line.rstrip()))

    if not headings:
        return 0

    dominant = headings[0][1]
    findings = [
        (lineno, style, raw)
        for lineno, style, raw in headings
        if style != dominant
    ]

    if not findings:
        return 0

    print(f"dominant ATX heading style: {dominant} (set by line {headings[0][0]})")
    for lineno, style, raw in findings:
        print(f"line {lineno}: {style} style heading breaks consistency: {raw!r}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
