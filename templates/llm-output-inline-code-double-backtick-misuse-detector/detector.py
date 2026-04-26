#!/usr/bin/env python3
"""
llm-output-inline-code-double-backtick-misuse-detector
======================================================

Detects inline-code spans delimited by **double backticks**
( ``...`` ) whose content **does not contain a literal
backtick**, e.g.:

    Use the ``foo`` function.
    The ``--verbose`` flag enables it.

CommonMark only requires double backticks when the span itself
contains a literal backtick (so the parser knows where the span
ends). When the content has no backtick, ``foo`` and `foo`
render identically, but the double form is harder to read in
source, easier to break under repair edits, and a strong signal
that the LLM cargo-culted a delimiter pattern from training
data without thinking about it.

One finding kind:

- `unnecessary_double_backtick`  — double-backtick inline span
  whose content has no literal backtick

The detector is deliberately conservative:

- Only flags **exactly two** opening / closing backticks. Triple
  or longer runs are out of scope (they are usually deliberate
  attempts to embed double-backticks themselves, or are fence
  fragments).
- Fenced code blocks (` ``` ` and `~~~`) are skipped wholesale
  so example Markdown in a tutorial does not self-trigger.
- Empty spans ( ```` `` `` ```` with nothing between, or only
  whitespace) are NOT flagged — those have separate semantics
  (CommonMark trims one space on each side).
- Backtick-content span ( ``` ``foo`bar`` ``` ) is NOT flagged
  — the double form is required there.
- Spans that span more than one line are NOT flagged (rare,
  fragile, separate concern).

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
# Match a double-backtick span on a single line. We require:
#   - two backticks (not preceded or followed by a third)
#   - content that does NOT itself contain two consecutive
#     backticks (which would be an early close)
#   - two backticks closing (not followed by a third)
# We capture content for the no-backtick check.
_DOUBLE_RE = re.compile(r"(?<!`)``([^`\n]*?(?:`[^`\n]+?)*?)``(?!`)")


def detect_unnecessary_double_backtick(lines: Iterable[str]) -> list[dict]:
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
        for match in _DOUBLE_RE.finditer(line):
            content = match.group(1)
            # Skip empty / whitespace-only spans (different
            # semantics under CommonMark).
            if not content.strip():
                continue
            # Skip if content has any literal backtick (then
            # the double form is required).
            if "`" in content:
                continue
            findings.append(
                {
                    "kind": "unnecessary_double_backtick",
                    "line_number": lineno,
                    "column": match.start() + 1,
                    "content": content,
                    "content_length": len(content),
                    "suggested_fix": f"`{content.strip()}`"
                    if content != content.strip()
                    else f"`{content}`",
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
    findings = detect_unnecessary_double_backtick(text.splitlines())
    payload = {"count": len(findings), "findings": findings, "ok": not findings}
    sys.stdout.write(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    )
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
