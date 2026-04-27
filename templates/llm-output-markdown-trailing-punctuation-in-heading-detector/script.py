#!/usr/bin/env python3
"""Detect ATX/setext headings that end with disallowed trailing punctuation.

LLMs often emit headings that end with a period, comma, semicolon, colon,
exclamation mark, or question mark — usually because they generated the
heading as a sentence first and forgot to strip the terminal punctuation.
This breaks markdownlint MD026 and produces awkward table-of-contents
entries (e.g. "Why this matters." or "Conclusion:") that read as
mid-sentence rather than as section titles.

This script flags every ATX heading (`# ...` through `###### ...`) and
every setext heading (line followed by `===` or `---` underline) whose
trimmed text ends with one of: `. , ; : ! ?`

The colon `:` is included by default because MD026's default
`punctuation` list is `.,;:!?`. Question marks in headings are common in
FAQ-style docs but are still flagged — strip them or change the heading
style if you want question-form headings.

Reads stdin, writes findings to stdout, exits 1 on findings, 0 on clean
input.
"""

from __future__ import annotations

import re
import sys

FENCE_RE = re.compile(r"^\s*(```|~~~)")
ATX_RE = re.compile(r"^\s{0,3}(#{1,6})\s+(.*?)\s*$")
SETEXT_UNDERLINE_RE = re.compile(r"^\s{0,3}(=+|-+)\s*$")

TRAILING_PUNCT = ".,;:!?"


def _strip_trailing_hashes(text: str) -> str:
    # ATX headings may have an optional trailing run of #s as a closer
    # ("# Heading ##"). Strip it before checking the real text.
    m = re.match(r"^(.*?)\s+#+\s*$", text)
    if m:
        return m.group(1).rstrip()
    return text.rstrip()


def _flag(heading_text: str) -> str | None:
    cleaned = heading_text.rstrip()
    if not cleaned:
        return None
    last = cleaned[-1]
    if last in TRAILING_PUNCT:
        return last
    return None


def main() -> int:
    lines = sys.stdin.read().splitlines()

    in_fence = False
    findings: list[str] = []

    for idx, line in enumerate(lines, start=1):
        if FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue

        # ATX heading.
        m = ATX_RE.match(line)
        if m:
            level = len(m.group(1))
            text = _strip_trailing_hashes(m.group(2))
            bad = _flag(text)
            if bad is not None:
                preview = text[:50]
                findings.append(
                    f"line {idx}: ATX heading (h{level}) ends with "
                    f"{bad!r}: {preview!r}"
                )
            continue

        # Setext heading: this line is the title, NEXT line is the
        # underline (=== or ---). Look ahead.
        if idx < len(lines):
            nxt = lines[idx]  # idx is 1-based, lines[idx] is the next 0-based
            if SETEXT_UNDERLINE_RE.match(nxt) and line.strip():
                # Make sure current line isn't itself a structural element.
                if not line.lstrip().startswith(("#", ">", "|", "-", "*", "+")):
                    text = line.strip()
                    bad = _flag(text)
                    if bad is not None:
                        underline_char = nxt.strip()[0]
                        level = 1 if underline_char == "=" else 2
                        preview = text[:50]
                        findings.append(
                            f"line {idx}: setext heading (h{level}) ends "
                            f"with {bad!r}: {preview!r}"
                        )

    if findings:
        for f in findings:
            print(f)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
