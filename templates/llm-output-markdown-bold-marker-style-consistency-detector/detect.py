#!/usr/bin/env python3
"""Detect mixed bold-emphasis marker styles in Markdown.

CommonMark allows two equivalent bold markers:

  **bold**
  __bold__

A document that mixes them within a single file is grammatically valid but
stylistically inconsistent — and a frequent LLM tell, since different
training corpora prefer different conventions.

This detector picks whichever style appears MORE OFTEN in the document as
the de-facto house style, then flags every occurrence of the OTHER style.
If the two styles tie (or only one appears), the document is clean.

Underscore bold inside a word (e.g. `foo__bar__baz`) is a common false
positive in CommonMark — the spec disallows intra-word `_` emphasis but
allows intra-word `*` emphasis. We detect bold runs only when surrounded
by whitespace, punctuation, or string boundaries on the OUTER side of the
opening / closing run, mirroring the spec's left/right flanking rules.

Exit codes:
  0 — clean (or single-style only)
  1 — mixed-style findings
  2 — usage / IO error
"""
from __future__ import annotations

import re
import sys

# Bold runs: ** or __ delimiting non-greedy content on a single line.
# We require the OUTER side to be a non-word character or string boundary
# to suppress intra-word false positives for `__`.
STAR_RE = re.compile(r"(?:(?<=\W)|(?<=^))\*\*(?=\S)(.+?)(?<=\S)\*\*(?=\W|$)")
UNDER_RE = re.compile(r"(?:(?<=\W)|(?<=^))__(?=\S)(.+?)(?<=\S)__(?=\W|$)")

FENCE_RE = re.compile(r"^\s{0,3}(`{3,}|~{3,})")


def _strip_fenced(lines: list[str]) -> list[tuple[int, str]]:
    """Yield (1-based-lineno, line) for lines OUTSIDE fenced code blocks."""
    out: list[tuple[int, str]] = []
    in_fence = False
    fence_char = ""
    for i, line in enumerate(lines, start=1):
        m = FENCE_RE.match(line)
        if m:
            ch = m.group(1)[0]
            if not in_fence:
                in_fence = True
                fence_char = ch
            elif ch == fence_char:
                in_fence = False
                fence_char = ""
            continue
        if in_fence:
            continue
        out.append((i, line))
    return out


def _strip_inline_code(line: str) -> str:
    """Replace inline `code` spans with spaces so embedded markers don't count."""
    out = []
    i = 0
    n = len(line)
    while i < n:
        if line[i] == "`":
            # find matching backtick
            j = line.find("`", i + 1)
            if j == -1:
                out.append(line[i])
                i += 1
                continue
            out.append(" " * (j - i + 1))
            i = j + 1
        else:
            out.append(line[i])
            i += 1
    return "".join(out)


def detect(path: str) -> int:
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.readlines()
    except OSError as e:
        print(f"error: cannot read {path}: {e}", file=sys.stderr)
        return 2

    star_hits: list[tuple[int, int, str]] = []
    under_hits: list[tuple[int, int, str]] = []

    for lineno, raw in _strip_fenced(lines):
        line = _strip_inline_code(raw.rstrip("\n"))
        for m in STAR_RE.finditer(line):
            star_hits.append((lineno, m.start() + 1, m.group(0)))
        for m in UNDER_RE.finditer(line):
            under_hits.append((lineno, m.start() + 1, m.group(0)))

    star_n, under_n = len(star_hits), len(under_hits)
    if star_n == 0 or under_n == 0:
        return 0  # single style — clean

    if star_n >= under_n:
        canonical, alt, alt_hits = "**bold**", "__bold__", under_hits
    else:
        canonical, alt, alt_hits = "__bold__", "**bold**", star_hits

    for lineno, col, text in alt_hits:
        print(
            f"{path}:{lineno}:{col}: bold-marker style mismatch — "
            f"found {alt} '{text}', document style is {canonical}"
        )

    print(f"\n{len(alt_hits)} finding(s)")
    return 1


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: detect.py <markdown-file>", file=sys.stderr)
        return 2
    return detect(argv[1])


if __name__ == "__main__":
    sys.exit(main(sys.argv))
