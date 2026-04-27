#!/usr/bin/env python3
"""Detect inconsistent fenced code-block fence shapes in markdown.

A fenced code block opens with a run of 3+ backticks or tildes (with up
to 3 leading spaces) and closes with a matching run of the same marker
character of length >= the opener. CommonMark permits openers of any
length, but mixing shapes within one document confuses naive extractors.

This detector identifies the dominant `(marker_char, fence_length)` pair
among all openers and flags every opener that differs.

Exit code: 0 clean, 1 if findings.
"""

from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path

_OPENER = re.compile(r"^( {0,3})(`{3,}|~{3,})(.*)$")


def _scan_openers(lines: list[str]) -> list[tuple[int, str, int]]:
    """Return list of (line_index, marker_char, fence_length) for each opener."""
    openers: list[tuple[int, str, int]] = []
    in_fence = False
    open_char = ""
    open_len = 0
    for i, line in enumerate(lines):
        if not in_fence:
            m = _OPENER.match(line)
            if m:
                fence = m.group(2)
                openers.append((i, fence[0], len(fence)))
                in_fence = True
                open_char = fence[0]
                open_len = len(fence)
        else:
            stripped = line.lstrip(" ")
            # Closer: same char, length >= opener, nothing else on the line.
            if (
                stripped
                and stripped[0] == open_char
                and len(stripped) >= open_len
                and set(stripped.rstrip()) == {open_char}
                and len(stripped.rstrip()) >= open_len
            ):
                in_fence = False
                open_char = ""
                open_len = 0
    return openers


def detect(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    lines = text.split("\n")
    openers = _scan_openers(lines)
    if len(openers) < 2:
        return []
    shapes = Counter((char, length) for _, char, length in openers)
    dominant_shape, _ = shapes.most_common(1)[0]
    dom_char, dom_len = dominant_shape
    dominant_str = dom_char * dom_len
    findings: list[str] = []
    for line_idx, char, length in openers:
        if (char, length) != dominant_shape:
            seen = char * length
            findings.append(
                f"{path}:{line_idx + 1}: fence opener "
                f"'{seen}' differs from dominant '{dominant_str}'"
            )
    return findings


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: detector.py FILE", file=sys.stderr)
        return 2
    findings = detect(Path(argv[1]))
    for f in findings:
        print(f)
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
