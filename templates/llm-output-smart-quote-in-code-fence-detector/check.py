#!/usr/bin/env python3
"""Detect "smart" (curly) quotation marks that leaked into fenced code
blocks in LLM output.

LLMs sometimes auto-curl quotes even inside ``` fenced blocks, which
breaks the snippet when copy-pasted into a shell, source file, or
JSON document. This checker scans a markdown document, isolates every
fenced code block, and reports every curly-quote character it finds
inside, with line and column.

Detected characters:
  U+2018  '  LEFT SINGLE QUOTATION MARK
  U+2019  '  RIGHT SINGLE QUOTATION MARK
  U+201C  "  LEFT DOUBLE QUOTATION MARK
  U+201D  "  RIGHT DOUBLE QUOTATION MARK
  U+2032  '  PRIME
  U+2033  "  DOUBLE PRIME

Stdlib only. Reads from argv[1] or STDIN.
Exit code: 0 when clean, 1 when any leak is found.
"""
from __future__ import annotations

import re
import sys


SMART = {
    "\u2018": "U+2018 LEFT SINGLE QUOTATION MARK",
    "\u2019": "U+2019 RIGHT SINGLE QUOTATION MARK",
    "\u201C": "U+201C LEFT DOUBLE QUOTATION MARK",
    "\u201D": "U+201D RIGHT DOUBLE QUOTATION MARK",
    "\u2032": "U+2032 PRIME",
    "\u2033": "U+2033 DOUBLE PRIME",
}

FENCE_RE = re.compile(r"^(?P<indent>[ \t]{0,3})(?P<fence>`{3,}|~{3,})(?P<info>[^\n]*)$")


def iter_fenced_blocks(lines):
    """Yield (start_line_1based, end_line_1based, info, body_lines).

    Body lines are returned with their absolute 1-based line numbers.
    """
    i = 0
    n = len(lines)
    while i < n:
        m = FENCE_RE.match(lines[i])
        if not m:
            i += 1
            continue
        fence_char = m.group("fence")[0]
        fence_len = len(m.group("fence"))
        info = m.group("info").strip()
        start = i + 1
        body = []
        j = i + 1
        closed = False
        while j < n:
            cm = FENCE_RE.match(lines[j])
            if cm and cm.group("fence")[0] == fence_char and len(cm.group("fence")) >= fence_len and cm.group("info").strip() == "":
                closed = True
                break
            body.append((j + 1, lines[j]))
            j += 1
        end = (j + 1) if closed else n
        yield start, end, info, body
        i = j + 1 if closed else n


def report(text: str) -> int:
    lines = text.splitlines()
    leaks = []  # (line, col, char, name, info)
    for start, end, info, body in iter_fenced_blocks(lines):
        for ln, content in body:
            for col_idx, ch in enumerate(content):
                if ch in SMART:
                    leaks.append((ln, col_idx + 1, ch, SMART[ch], info or "(no language tag)"))
    if not leaks:
        print("OK: no smart quotes found inside fenced code blocks")
        return 0
    print(f"Found {len(leaks)} smart-quote leak(s) inside fenced code blocks:")
    for ln, col, ch, name, info in leaks:
        print(f"  line {ln} col {col}: {ch!r} {name}  [block: {info}]")
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
