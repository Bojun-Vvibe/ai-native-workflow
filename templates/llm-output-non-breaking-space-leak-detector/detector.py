#!/usr/bin/env python3
"""Detect non-breaking-space and other non-standard whitespace leaks in LLM output.

LLMs often emit U+00A0 (NBSP), U+202F (narrow NBSP), U+2007 (figure space),
U+2009 (thin space), and U+3000 (ideographic space) where a regular ASCII
space was intended. These break grep/sort/diff and confuse tokenizers.

Usage:
    python3 detector.py <file>

Exits non-zero if any leaks are found.
"""
import sys

# Map of codepoint -> (label, ascii suggestion)
TARGETS = {
    "\u00A0": ("U+00A0 NO-BREAK SPACE", " "),
    "\u202F": ("U+202F NARROW NO-BREAK SPACE", " "),
    "\u2007": ("U+2007 FIGURE SPACE", " "),
    "\u2009": ("U+2009 THIN SPACE", " "),
    "\u200A": ("U+200A HAIR SPACE", " "),
    "\u3000": ("U+3000 IDEOGRAPHIC SPACE", " "),
}


def scan(path: str) -> int:
    hits = 0
    with open(path, "r", encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, 1):
            for col, ch in enumerate(line, 1):
                if ch in TARGETS:
                    label, _ = TARGETS[ch]
                    ctx = line.rstrip("\n")
                    print(f"{path}:{lineno}:{col}: {label}")
                    print(f"    context: {ctx!r}")
                    hits += 1
    return hits


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: detector.py <file> [<file>...]", file=sys.stderr)
        return 2
    total = 0
    for p in argv[1:]:
        total += scan(p)
    if total:
        print(f"\nFAIL: {total} non-standard whitespace leak(s) detected")
        return 1
    print("OK: no non-standard whitespace leaks")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
