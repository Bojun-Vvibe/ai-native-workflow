#!/usr/bin/env python3
"""
llm-output-heading-trailing-period-detector
===========================================

Detects ATX-style Markdown headings (`#`, `##`, …, `######`) that
end with terminal sentence punctuation:

    ## Why this matters.
    ### Conclusion!
    #### Open questions?

Headings are titles, not sentences. Most house style guides
(Google, GitLab, MDN, the Chicago Manual when used for
headings) explicitly forbid trailing `.`, `!`, or `?` on
headings. LLMs introduce these constantly because their training
data is mostly running prose where every clause ends with a
terminator.

Three finding kinds:

- `trailing_period`         — heading ends with `.` (most common)
- `trailing_exclamation`    — heading ends with `!`
- `trailing_question_mark`  — heading ends with `?`

Trailing whitespace and the optional ATX closing hashes
(`## Heading ##`) are stripped before the check, so
`## Heading. ##` and `## Heading.   ` both fire.

Setext headings (underlined with `===` / `---`) are out of
scope — they are rare in LLM output and have a different shape.

Fenced code blocks (` ``` ` and `~~~`) are skipped wholesale.
Lines that look like headings inside a fence (e.g. example
Markdown in a tutorial) are NOT flagged.

Ellipsis (`…` or `...`) at end of heading is **NOT** flagged —
it carries deliberate "more to come" semantics and is common
in slide-deck-style headings.

Abbreviations and version numbers ending in `.` (`v1.0.`,
`Mr.`, `etc.`) are still flagged, because at heading position
the right fix is "remove the period", not "preserve it".

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

# ATX heading: 1-6 hashes, then required space, then text.
# Optional trailing closing hashes (with optional space before).
_HEADING_RE = re.compile(
    r"^(?P<indent>\s{0,3})(?P<hashes>#{1,6})\s+(?P<text>.+?)(?:\s+#+\s*)?$"
)
_FENCE_RE = re.compile(r"^\s{0,3}(```+|~~~+)")

# Map terminal punctuation -> finding kind. Order matters for
# the ellipsis check below.
_TERMINATORS = {
    ".": "trailing_period",
    "!": "trailing_exclamation",
    "?": "trailing_question_mark",
}


def _strip_trailing_ws(s: str) -> str:
    return s.rstrip(" \t")


def _is_ellipsis_ending(text: str) -> bool:
    """True if text ends with `…` or `...` (deliberate, not flagged)."""
    if text.endswith("\u2026"):
        return True
    if text.endswith("..."):
        return True
    return False


def detect_heading_trailing_punct(lines: Iterable[str]) -> list[dict]:
    findings: list[dict] = []
    in_fence = False
    fence_marker: str | None = None
    for lineno, raw in enumerate(lines, start=1):
        line = raw.rstrip("\n")
        m = _FENCE_RE.match(line)
        if m:
            marker = m.group(1)[0] * 3
            if not in_fence:
                in_fence = True
                fence_marker = marker
            elif fence_marker == marker:
                in_fence = False
                fence_marker = None
            continue
        if in_fence:
            continue
        hm = _HEADING_RE.match(line)
        if not hm:
            continue
        text = _strip_trailing_ws(hm.group("text"))
        if not text:
            continue
        if _is_ellipsis_ending(text):
            continue
        last = text[-1]
        if last not in _TERMINATORS:
            continue
        findings.append(
            {
                "kind": _TERMINATORS[last],
                "level": len(hm.group("hashes")),
                "line_number": lineno,
                "heading_text": text,
                "terminator": last,
            }
        )
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
    findings = detect_heading_trailing_punct(text.splitlines())
    payload = {"count": len(findings), "findings": findings, "ok": not findings}
    sys.stdout.write(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
