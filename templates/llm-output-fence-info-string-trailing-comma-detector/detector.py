#!/usr/bin/env python3
"""Detect fenced-code-block info strings with stray punctuation.

LLMs frequently emit code fences like:

    ```python,
    ```js;
    ```bash:
    ```ts.

The trailing comma / semicolon / colon / period is not part of any
recognized info-string syntax and turns the language tag into an
unknown token (`python,`), so syntax highlighting silently falls back
to plain text.

This detector flags any opening code fence whose info string ends with
one of: `,` `;` `:` `.` `!` (with optional trailing whitespace).

Pure stdlib. Single pass. Exit 0 = clean, 1 = findings, 2 = usage.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

# Opening fence: at least 3 backticks or tildes, then info string
FENCE_OPEN_RE = re.compile(r"^(\s{0,3})(`{3,}|~{3,})([^`\n]*)$")
TRAILING_PUNCT_RE = re.compile(r"^[A-Za-z0-9_+\-./]+([,;:.!])\s*$")


def scan(path: Path) -> list[tuple[int, str]]:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    findings: list[tuple[int, str]] = []
    in_fence = False
    fence_marker = ""

    for lineno, line in enumerate(lines, 1):
        if not in_fence:
            m = FENCE_OPEN_RE.match(line)
            if m:
                marker = m.group(2)
                info = m.group(3).strip()
                in_fence = True
                fence_marker = marker[0] * 3  # for matching close
                if not info:
                    continue
                pm = TRAILING_PUNCT_RE.match(info)
                if pm:
                    findings.append((
                        lineno,
                        f"code fence info string '{info}' ends with '{pm.group(1)}' "
                        f"(language tag becomes unknown — strip the punctuation)",
                    ))
        else:
            # Look for closing fence (same kind, length >= 3)
            stripped = line.strip()
            if stripped.startswith(fence_marker[0] * 3) and set(stripped) <= {fence_marker[0]}:
                in_fence = False

    return findings


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: detector.py FILE [FILE ...]", file=sys.stderr)
        return 2
    total = 0
    for arg in argv[1:]:
        p = Path(arg)
        if not p.is_file():
            print(f"skip (not a file): {arg}", file=sys.stderr)
            continue
        for lineno, msg in scan(p):
            print(f"{p}:{lineno}: {msg}")
            total += 1
    if total:
        print(f"\n{total} finding(s).", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
