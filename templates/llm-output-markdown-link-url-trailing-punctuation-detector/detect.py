#!/usr/bin/env python3
"""Detect markdown inline links whose URL ends with sentence
punctuation that was almost certainly meant to live OUTSIDE the
link target.

LLMs frequently emit text like:

    See [the docs](https://example.com/page.).

Here the trailing '.' is a sentence-terminator that got captured
inside the URL, producing a 404. The model should have written:

    See [the docs](https://example.com/page).

This detector flags any inline link of the form `[text](url)` whose
URL ends with one of: . , ; : ! ? ).

It is **code-fence aware** (skips ``` / ~~~ blocks) and ignores
inline-code spans (text between single backticks on the same line).

Exit codes:
  0 = no findings
  1 = findings printed to stdout
  2 = usage error
"""
from __future__ import annotations

import re
import sys

FENCE_RE = re.compile(r"^\s*(```+|~~~+)")
# Inline link: [text](url) where url has no spaces and no nested parens.
# We deliberately do not try to match link titles.
LINK_RE = re.compile(r"\[([^\]\n]+)\]\(([^)\s]+)\)")
TRAILING_BAD = ".,;:!?"


def strip_inline_code(line: str) -> str:
    """Replace inline-code spans with spaces of equal length so that
    column positions are preserved but their contents are not scanned."""
    out = []
    in_code = False
    for ch in line:
        if ch == "`":
            in_code = not in_code
            out.append(" ")
        elif in_code:
            out.append(" ")
        else:
            out.append(ch)
    return "".join(out)


def scan(text: str):
    in_fence = False
    findings = []
    for i, raw in enumerate(text.splitlines(), 1):
        if FENCE_RE.match(raw):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        scrubbed = strip_inline_code(raw)
        for m in LINK_RE.finditer(scrubbed):
            url = m.group(2)
            if url and url[-1] in TRAILING_BAD:
                findings.append((i, m.start(), url, raw.rstrip("\n")))
    return findings


def main(argv):
    if len(argv) != 2:
        print("usage: detect.py <file.md>", file=sys.stderr)
        return 2
    with open(argv[1], "r", encoding="utf-8") as f:
        text = f.read()
    findings = scan(text)
    for line, col, url, raw in findings:
        print(f"{argv[1]}:{line}:{col+1}: link URL ends with {url[-1]!r}: {url}")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
