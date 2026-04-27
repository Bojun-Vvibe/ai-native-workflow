#!/usr/bin/env python3
"""Detect markdown inline links/images whose link-text has leading or
trailing whitespace inside the brackets.

LLMs frequently emit links shaped like ``[ click here ](https://x)`` or
``[text  ](https://x)`` — usually because the model first produced the
phrase with surrounding spaces and then wrapped the brackets without
trimming. CommonMark renders these by *keeping* the whitespace, which
produces visibly underlined leading/trailing spaces, breaks anchor-text
matching in downstream tooling (analytics, citation extractors, link
checkers that hash anchor text), and trips lint rules such as
markdownlint MD039.

This validator flags both inline links ``[text](url)`` and inline
images ``![alt](url)`` whose bracketed text has at least one leading
or trailing whitespace character. Reference-style links
(``[text][ref]``) are also covered.

Reads stdin, writes findings to stdout, exits ``1`` on any finding,
``0`` on a clean document.

Scope rules:

- Code spans (`` `...` ``) and fenced code blocks (``` ``` ```/``~~~``)
  are skipped — anything inside them is treated as literal text, not
  markdown.
- Empty link text ``[](...)`` is *not* flagged here; that is a
  different finding class handled by other validators.
- A link text that is only whitespace (e.g. ``[   ](url)``) is also not
  flagged here, for the same reason — it is empty-text, not edge-space.
"""

from __future__ import annotations

import re
import sys

FENCE_RE = re.compile(r"^\s*(```|~~~)")

# Match an inline link or image: optional `!`, then `[text](url...)`.
# We deliberately stop link-text at the first unescaped `]` and require
# a matching `(` immediately after — that is enough to skip reference
# links of the form `[text][ref]` here (handled separately below).
INLINE_LINK_RE = re.compile(r"(!?)\[([^\[\]\n]*?)\]\(")

# Reference-style link: `[text][ref]` — `ref` is allowed to be empty
# (collapsed reference, e.g. `[text][]`).
REFERENCE_LINK_RE = re.compile(r"(!?)\[([^\[\]\n]*?)\]\[[^\[\]\n]*?\]")


def _strip_code_spans(line: str) -> str:
    """Replace inline code spans with same-length placeholder so that
    column positions are preserved while their contents are masked.

    Backtick runs of equal length open and close a code span. We do a
    minimal pass that handles single- and multi-backtick runs.
    """
    out_chars = list(line)
    i = 0
    n = len(line)
    while i < n:
        if line[i] == "`":
            # Determine run length.
            j = i
            while j < n and line[j] == "`":
                j += 1
            run = j - i
            tick = "`" * run
            # Find closing run of identical length.
            close = line.find(tick, j)
            if close == -1:
                # Unterminated — leave the rest alone, just advance.
                i = j
                continue
            # Mask everything between i and close+run with spaces, but
            # keep the backticks themselves so any link-pattern outside
            # this span is still anchored correctly.
            for k in range(j, close):
                out_chars[k] = " "
            i = close + run
        else:
            i += 1
    return "".join(out_chars)


def _check_text(kind: str, text: str, line_no: int, col: int) -> str | None:
    if not text:
        # Empty link text — not our concern.
        return None
    if not text.strip():
        # All-whitespace text — also empty-text, not edge-space.
        return None
    leading = len(text) - len(text.lstrip())
    trailing = len(text) - len(text.rstrip())
    if leading == 0 and trailing == 0:
        return None
    where = []
    if leading:
        where.append(f"leading={leading}")
    if trailing:
        where.append(f"trailing={trailing}")
    preview = text if len(text) <= 40 else text[:37] + "..."
    return (
        f"line {line_no}: col {col}: {kind} link text has edge whitespace "
        f"({', '.join(where)}): {preview!r}"
    )


def main() -> int:
    raw_lines = sys.stdin.read().splitlines()
    in_fence = False
    findings: list[str] = []

    for idx, raw in enumerate(raw_lines, start=1):
        if FENCE_RE.match(raw):
            in_fence = not in_fence
            continue
        if in_fence:
            continue

        line = _strip_code_spans(raw)

        for m in INLINE_LINK_RE.finditer(line):
            bang = m.group(1)
            text = m.group(2)
            kind = "inline image" if bang else "inline"
            f = _check_text(kind, text, idx, m.start() + 1)
            if f:
                findings.append(f)

        for m in REFERENCE_LINK_RE.finditer(line):
            bang = m.group(1)
            text = m.group(2)
            kind = "reference image" if bang else "reference"
            f = _check_text(kind, text, idx, m.start() + 1)
            if f:
                findings.append(f)

    if findings:
        for f in findings:
            print(f)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
