#!/usr/bin/env python3
"""
llm-output-hyperlink-empty-text-detector
========================================

Detects Markdown inline hyperlinks whose visible link text is
empty or whitespace-only:

    [](https://example.com)
    [   ](https://example.com)
    [\u00a0](https://example.com)   # NBSP-only text

Why this matters: an empty `[]` renders as a zero-width clickable
region in most Markdown renderers (GitHub, GitLab, MkDocs). The
link is still live but completely invisible to readers and
screen readers. LLMs produce this when they "remember" they
should cite something but lose the anchor text mid-stream.

Three finding kinds:

- `empty_text`            — `[]` (literally nothing between brackets)
- `whitespace_only_text`  — only ASCII whitespace between brackets
- `invisible_only_text`   — only non-ASCII whitespace (NBSP, ZWSP,
                            ideographic space, em space) — reported
                            separately because the failure mode is
                            different (the model emitted *something*
                            but it was an invisible byte).

Fenced code blocks (``` and ~~~) are skipped wholesale so
documented examples of bad links do not trigger the detector.

Reference-style links (`[text][ref]` and `[ref]: url`) are out
of scope; the orphan-reference variant is covered by
`llm-output-link-reference-definition-orphan-detector`.

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

# [TEXT](URL).  TEXT may be empty.  URL must be non-empty and not
# contain an unescaped ')' to keep the regex linear and safe.
_LINK_RE = re.compile(r"\[(?P<text>[^\[\]\n]*)\]\((?P<url>[^()\s][^()\n]*)\)")

# Whitespace classes
_ASCII_WS = set(" \t")
# Common invisible / non-ASCII whitespace seen leaking from LLMs.
_INVISIBLE_WS = {
    "\u00a0",  # NBSP
    "\u200b",  # ZERO WIDTH SPACE
    "\u200c",  # ZERO WIDTH NON-JOINER
    "\u200d",  # ZERO WIDTH JOINER
    "\u2002",  # EN SPACE
    "\u2003",  # EM SPACE
    "\u2009",  # THIN SPACE
    "\u202f",  # NARROW NO-BREAK SPACE
    "\u3000",  # IDEOGRAPHIC SPACE
    "\ufeff",  # ZERO WIDTH NO-BREAK SPACE / BOM
}

_FENCE_RE = re.compile(r"^\s{0,3}(```+|~~~+)")


def _classify(text: str) -> str | None:
    """Return finding-kind for empty/whitespace text, else None."""
    if text == "":
        return "empty_text"
    chars = set(text)
    if chars <= _ASCII_WS:
        return "whitespace_only_text"
    if chars <= (_ASCII_WS | _INVISIBLE_WS) and (chars & _INVISIBLE_WS):
        return "invisible_only_text"
    return None


def detect_empty_link_text(lines: Iterable[str]) -> list[dict]:
    findings: list[dict] = []
    in_fence = False
    fence_marker: str | None = None
    for lineno, raw in enumerate(lines, start=1):
        line = raw.rstrip("\n")
        m = _FENCE_RE.match(line)
        if m:
            marker = m.group(1)[0] * 3  # normalise to 3 chars
            if not in_fence:
                in_fence = True
                fence_marker = marker
            elif fence_marker == marker:
                in_fence = False
                fence_marker = None
            continue
        if in_fence:
            continue
        for lm in _LINK_RE.finditer(line):
            text = lm.group("text")
            kind = _classify(text)
            if kind is None:
                continue
            findings.append(
                {
                    "kind": kind,
                    "line_number": lineno,
                    "column": lm.start() + 1,
                    "url": lm.group("url"),
                    "raw_text": text,
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
    findings = detect_empty_link_text(text.splitlines())
    payload = {"count": len(findings), "findings": findings, "ok": not findings}
    sys.stdout.write(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
