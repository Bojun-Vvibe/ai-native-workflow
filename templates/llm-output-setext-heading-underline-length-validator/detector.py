#!/usr/bin/env python3
"""
llm-output-setext-heading-underline-length-validator
====================================================

Detects setext-style Markdown headings whose underline is
**shorter than the heading text** (after stripping trailing
whitespace), e.g.:

    My Heading
    ===

    Subheading
    --

CommonMark accepts any setext underline length >= 1, so these
render as headings. But every renderer that does soft visual
alignment (most doc sites, GitHub's preview, pandoc with some
templates) leaves a stubby underline that looks like a typo. It
also signals that the LLM was counting characters poorly, which
correlates with other length-related drift downstream.

Two finding kinds:

- `setext_underline_too_short_h1`  — `=` underline shorter than
  the visible heading text length
- `setext_underline_too_short_h2`  — same, but for `-` underline

The detector is deliberately conservative:

- Only flags when underline length is **strictly less than**
  text length. Equal-length is fine. Longer is fine.
- Heading text length is measured in **Unicode code points**
  after stripping trailing whitespace. CJK width is NOT
  doubled — a 4-char CJK heading just needs a 4-char underline,
  matching CommonMark's definition.
- The underline line must be pure `=`/`-` (with optional
  leading 0-3 spaces and trailing whitespace). A line with any
  other content is not a setext underline at all.
- Fenced code blocks (` ``` ` and `~~~`) are skipped wholesale,
  so example Markdown in a tutorial does not self-trigger.
- A blank line between text and underline disqualifies setext
  per CommonMark; we honour that and do not flag.
- An H2 underline (`---`) directly under text where the text
  could also be a list item or a paragraph is still a setext
  heading per CommonMark precedence rules; we follow CommonMark
  and flag it.

Usage:
    python3 detector.py [FILE ...]   # FILEs, or stdin if none

Exit code: 0 clean, 1 at least one finding. JSON to stdout.
Pure stdlib.
"""
from __future__ import annotations

import json
import re
import sys
from typing import Iterable

_FENCE_RE = re.compile(r"^\s{0,3}(```+|~~~+)")
# A setext underline: 0-3 leading spaces, then 1+ of `=` or `-`,
# then optional trailing whitespace, nothing else.
_UNDERLINE_RE = re.compile(r"^\s{0,3}(?P<run>=+|-+)\s*$")


def detect_short_setext_underlines(lines_input: Iterable[str]) -> list[dict]:
    lines = [ln.rstrip("\n") for ln in lines_input]
    findings: list[dict] = []
    in_fence = False
    fence_marker: str | None = None

    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        m = _FENCE_RE.match(line)
        if m:
            marker = m.group(1)[0] * 3
            if not in_fence:
                in_fence = True
                fence_marker = marker
            elif fence_marker == marker:
                in_fence = False
                fence_marker = None
            i += 1
            continue
        if in_fence:
            i += 1
            continue

        # A setext heading needs: non-blank text line, then on
        # the very next line a pure `=`/`-` run.
        if i + 1 >= n:
            i += 1
            continue
        text_raw = line
        underline_raw = lines[i + 1]

        text_stripped = text_raw.rstrip()
        # Text line must be non-blank.
        if not text_stripped.strip():
            i += 1
            continue

        um = _UNDERLINE_RE.match(underline_raw)
        if not um:
            i += 1
            continue

        run = um.group("run")
        # Use code-point length of the trimmed text.
        text_len = len(text_stripped.lstrip())
        underline_len = len(run)

        if underline_len < text_len:
            kind = (
                "setext_underline_too_short_h1"
                if run[0] == "="
                else "setext_underline_too_short_h2"
            )
            findings.append(
                {
                    "kind": kind,
                    "line_number": i + 2,  # the underline line
                    "heading_line_number": i + 1,
                    "heading_text": text_stripped.lstrip(),
                    "heading_text_length": text_len,
                    "underline_char": run[0],
                    "underline_length": underline_len,
                    "shortfall": text_len - underline_len,
                }
            )
        # Advance past the heading + underline pair.
        i += 2

    return findings


def _read_input(argv: list[str]) -> str:
    if len(argv) <= 1:
        return sys.stdin.read()
    chunks: list[str] = []
    for path in argv[1:]:
        with open(path, "r", encoding="utf-8") as f:
            chunks.append(f.read())
    return "".join(chunks)


def main(argv: list[str]) -> int:
    text = _read_input(argv)
    findings = detect_short_setext_underlines(text.splitlines())
    payload = {"count": len(findings), "findings": findings, "ok": not findings}
    sys.stdout.write(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    )
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
