#!/usr/bin/env python3
"""Detect ATX headings that are immediately followed by a non-blank, non-heading line.

CommonMark renders `# H\nbody` correctly: the body is its own paragraph. But by
near-universal convention (and most Markdown style guides — markdownlint MD022,
remark-lint, prettier, mdformat) an ATX heading should be followed by a blank
line before the next paragraph / list / code block.

LLM outputs frequently violate this when:

  - The model emits a heading and immediately starts the body in the same
    streamed turn without inserting the canonical blank line.
  - A repair pass joins two chunks and drops the separating blank line.
  - The model imitates a "compact" style (often seen in OSS READMEs that use
    setext + blank-line conventions) inconsistently with its own ATX use.

The visual rendering is fine, but downstream tooling that uses the blank line
as a section delimiter (TOC builders, chunkers for retrieval, naive splitters)
breaks. It also makes diffs noisier when later edits insert / remove the
heading.

Strategy
--------
- Scan the file line-by-line.
- Skip fenced code blocks (``` and ~~~).
- An ATX heading line matches `^ {0,3}#{1,6}(\\s|$)`.
- For each heading line, check the next line:
    * If EOF -> ok (heading is last line).
    * If blank (whitespace-only) -> ok.
    * If another ATX heading -> ok (consecutive headings need no blank between).
    * Otherwise -> flag as missing-blank-line-after-heading.

Exit codes
----------
  0 = clean
  1 = at least one heading missing the trailing blank line
  2 = usage / IO error
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


ATX_HEADING_RE = re.compile(r"^ {0,3}#{1,6}(?:\s|$)")
FENCE_CHARS = ("```", "~~~")


def is_atx_heading(line: str) -> bool:
    return bool(ATX_HEADING_RE.match(line))


def find_findings(text: str) -> list[tuple[int, str]]:
    """Return list of (lineno_of_heading, snippet_of_following_line)."""
    findings: list[tuple[int, str]] = []
    lines = text.splitlines()

    in_fence = False
    fence_marker = ""

    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.lstrip()
        if not in_fence:
            for marker in FENCE_CHARS:
                if stripped.startswith(marker):
                    in_fence = True
                    fence_marker = marker
                    break
            if in_fence:
                i += 1
                continue
        else:
            if stripped.startswith(fence_marker):
                in_fence = False
                fence_marker = ""
            i += 1
            continue

        if is_atx_heading(line):
            # Check the next line
            if i + 1 < len(lines):
                nxt = lines[i + 1]
                if nxt.strip() == "":
                    pass  # blank -> ok
                elif is_atx_heading(nxt):
                    pass  # consecutive heading -> ok
                else:
                    snippet = nxt.strip()[:60]
                    findings.append((i + 1, snippet))
            # EOF after heading -> ok
        i += 1

    return findings


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(f"usage: {argv[0]} <file.md> [<file2.md> ...]", file=sys.stderr)
        return 2

    any_hits = False
    for arg in argv[1:]:
        path = Path(arg)
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        findings = find_findings(text)
        for lineno, snippet in findings:
            print(
                f"{path}:{lineno}:1: heading-blank-line-after-missing "
                f"(next_line={snippet!r})"
            )
        if findings:
            any_hits = True

    return 1 if any_hits else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
