#!/usr/bin/env python3
"""
llm-output-markdown-hard-line-break-style-mix-detector

Detects when a single Markdown document mixes multiple "hard line
break" styles:

  1. Trailing two-or-more spaces at end of line (CommonMark canonical)
  2. Trailing backslash `\\` at end of line (CommonMark alternate)
  3. Inline `<br>` / `<br/>` / `<br />` HTML tags

Each style produces an identical rendered result, but mixing them in
one document is a low-grade quality smell typical of LLM output
patched together from different sources.

Code-fence aware: hard-break candidates inside fenced code blocks
(``` or ~~~) are ignored. Inline code spans are also stripped.

Exit codes:
  0 - clean (zero or one style present)
  1 - mix detected (>=2 distinct styles)
  2 - usage error
"""

from __future__ import annotations

import re
import sys
from typing import List, Tuple


FENCE_RE = re.compile(r"^(\s{0,3})(```+|~~~+)(.*)$")
TRAILING_SPACES_RE = re.compile(r" {2,}$")
TRAILING_BACKSLASH_RE = re.compile(r"(?<!\\)\\$")
BR_TAG_RE = re.compile(r"<br\s*/?\s*>", re.IGNORECASE)


def strip_inline_code(line: str) -> str:
    """Replace inline `code spans` with spaces so matches inside them are ignored."""
    out = []
    i = 0
    n = len(line)
    while i < n:
        if line[i] == "`":
            j = i
            while j < n and line[j] == "`":
                j += 1
            tick_run = line[i:j]
            close = line.find(tick_run, j)
            if close == -1:
                out.append(line[i:])
                return "".join(out)
            out.append(" " * (close + len(tick_run) - i))
            i = close + len(tick_run)
        else:
            out.append(line[i])
            i += 1
    return "".join(out)


def find_breaks(path: str) -> Tuple[List[Tuple[int, str, str]], dict]:
    """Return (findings, counts_by_style)."""
    findings: List[Tuple[int, str, str]] = []
    counts = {"trailing-spaces": 0, "trailing-backslash": 0, "br-tag": 0}

    in_fence = False
    fence_marker: str | None = None

    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        lines = fh.readlines()

    for lineno, raw in enumerate(lines, start=1):
        # Preserve trailing whitespace; only strip the newline itself.
        line = raw.rstrip("\n").rstrip("\r")

        m = FENCE_RE.match(line)
        if m:
            marker = m.group(2)[0] * 3
            if not in_fence:
                in_fence = True
                fence_marker = marker
                continue
            else:
                if fence_marker and line.lstrip().startswith(fence_marker):
                    in_fence = False
                    fence_marker = None
                continue

        if in_fence:
            continue

        # Trailing-spaces only count as a hard break if the next line is
        # non-blank (CommonMark) — and the line itself isn't just spaces.
        is_last = lineno == len(lines)
        next_blank = True
        if not is_last:
            nxt = lines[lineno].rstrip("\n").rstrip("\r")
            next_blank = (nxt.strip() == "")
        line_has_content = line.strip() != ""

        if line_has_content and not next_blank and TRAILING_SPACES_RE.search(line):
            counts["trailing-spaces"] += 1
            findings.append((lineno, "trailing-spaces", repr(line[-6:])))

        if line_has_content and not next_blank and TRAILING_BACKSLASH_RE.search(line):
            counts["trailing-backslash"] += 1
            findings.append((lineno, "trailing-backslash", repr(line[-6:])))

        scrub = strip_inline_code(line)
        for m in BR_TAG_RE.finditer(scrub):
            counts["br-tag"] += 1
            findings.append((lineno, "br-tag", m.group(0)))

    findings.sort(key=lambda t: t[0])
    return findings, counts


def main(argv: List[str]) -> int:
    if len(argv) != 2:
        print(f"usage: {argv[0]} <file.md>", file=sys.stderr)
        return 2

    path = argv[1]
    findings, counts = find_breaks(path)

    print(f"file: {path}")
    print(
        f"hard-break occurrences: "
        f"trailing-spaces={counts['trailing-spaces']}, "
        f"trailing-backslash={counts['trailing-backslash']}, "
        f"br-tag={counts['br-tag']}"
    )

    distinct = sum(1 for v in counts.values() if v > 0)
    if distinct >= 2:
        print(f"MIX DETECTED: {distinct} distinct hard-break styles in same document")
        for lineno, style, snippet in findings:
            print(f"  line {lineno} [{style}]: {snippet}")
        return 1

    print("OK: at most one hard-break style present")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
