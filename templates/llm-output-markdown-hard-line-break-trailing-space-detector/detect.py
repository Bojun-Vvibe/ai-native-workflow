#!/usr/bin/env python3
"""Detect Markdown hard-line-break trailing spaces (the "two trailing spaces"
pattern that renders as <br>) in LLM output where they are almost certainly
unintended.

Markdown's hard line break = a line ending in 2+ trailing spaces followed by
a newline. LLMs frequently emit this by accident (e.g. word-wrapping in
training data), creating invisible <br> tags that break diff hygiene and
downstream Markdown-to-plaintext conversion.

What is flagged:
  * Any non-blank line ending in two or more space characters before the
    newline.

Ignored:
  * Lines inside fenced code blocks (``` or ~~~).
  * Indented (4-space) code blocks where the trailing spaces follow code
    content — those don't render as <br> anyway, but to keep the rule
    simple we still report them outside fenced blocks. (LLMs rarely
    intentionally hard-break inside indented code.)
  * Blank lines (only whitespace).

Stdlib only. Exit 0 if clean, 1 if findings, 2 on usage error.
"""
from __future__ import annotations

import re
import sys

FENCE_RE = re.compile(r"^\s*(```+|~~~+)")


def scan(path: str) -> int:
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except OSError as exc:
        print(f"error: cannot read {path}: {exc}", file=sys.stderr)
        return 2

    findings: list[str] = []
    in_fence = False
    fence_marker = ""

    for lineno, raw in enumerate(lines, start=1):
        # Strip only the trailing newline, preserve trailing spaces
        if raw.endswith("\r\n"):
            line = raw[:-2]
        elif raw.endswith("\n"):
            line = raw[:-1]
        else:
            line = raw

        fm = FENCE_RE.match(line)
        if fm:
            tok = fm.group(1)
            if not in_fence:
                in_fence = True
                fence_marker = tok[0]
            elif tok[0] == fence_marker:
                in_fence = False
                fence_marker = ""
            continue
        if in_fence:
            continue
        if not line.strip():
            continue

        # Count trailing spaces
        stripped_right = line.rstrip(" ")
        trailing = len(line) - len(stripped_right)
        if trailing >= 2:
            preview = stripped_right[-40:] if len(stripped_right) > 40 else stripped_right
            findings.append(
                f"{path}:{lineno}: hard-line-break trailing spaces ({trailing}) after: {preview!r}"
            )

    if findings:
        for f in findings:
            print(f)
        print(f"\n{len(findings)} finding(s)")
        return 1
    return 0


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: detect.py <file.md>", file=sys.stderr)
        return 2
    return scan(argv[1])


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
