#!/usr/bin/env python3
"""Detect setext-style markdown headings whose underline length does
not match the heading text length.

A setext heading is two consecutive lines:

    Heading Text
    ============

or

    Heading Text
    ------------

CommonMark only requires the underline to be >=1 char, but
stylistically LLM-emitted markdown should keep the underline length
equal to the heading text length. This detector flags any setext
heading where len(underline) != len(text.rstrip()).

Code-fence aware: lines inside fenced code blocks (``` or ~~~) are
skipped.

Exit codes:
  0 = no findings
  1 = findings printed to stdout
  2 = usage error
"""
from __future__ import annotations

import re
import sys

FENCE_RE = re.compile(r"^\s*(```+|~~~+)")
UNDERLINE_RE = re.compile(r"^\s*(=+|-+)\s*$")


def scan(text: str):
    lines = text.splitlines()
    in_fence = False
    findings = []
    fence_state = []  # parallel array: True if line i is inside a fence
    for raw in lines:
        if FENCE_RE.match(raw):
            fence_state.append(in_fence)  # fence marker line itself
            in_fence = not in_fence
        else:
            fence_state.append(in_fence)

    for i in range(len(lines) - 1):
        if fence_state[i] or fence_state[i + 1]:
            continue
        text_line = lines[i]
        underline = lines[i + 1]
        if not text_line.strip():
            continue
        # Skip if text line itself looks like an ATX heading
        if text_line.lstrip().startswith("#"):
            continue
        m = UNDERLINE_RE.match(underline)
        if not m:
            continue
        # Skip thematic-break-style "---" with spaces between dashes
        u_stripped = underline.strip()
        # Skip if underline is just dashes but text line is empty/blank above
        # (would be a thematic break, not a setext heading)
        text_stripped = text_line.strip()
        if not text_stripped:
            continue
        # If preceding line (i-1) is blank or i==0, this is a real setext heading
        if i > 0 and lines[i - 1].strip() and not text_line.startswith(" "):
            # could still be setext if previous para; CommonMark allows it,
            # but to keep this conservative we only flag when text_line is
            # the start of a "block": i==0 or prev line blank
            pass
        # Conservative: require previous line blank or BOF
        if i > 0 and lines[i - 1].strip() != "":
            continue
        t_len = len(text_stripped)
        u_len = len(u_stripped)
        if t_len != u_len:
            delta = u_len - t_len
            findings.append((i + 2, u_len, t_len, delta, underline.rstrip("\n")))
    return findings


def main(argv):
    if len(argv) != 2:
        print("usage: detect.py <file.md>", file=sys.stderr)
        return 2
    with open(argv[1], "r", encoding="utf-8") as f:
        text = f.read()
    findings = scan(text)
    for line, u_len, t_len, delta, raw in findings:
        sign = "+" if delta > 0 else ""
        print(
            f"{argv[1]}:{line}: setext underline length {u_len} != "
            f"heading text length {t_len} (delta {sign}{delta}): {raw}"
        )
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
