#!/usr/bin/env python3
"""Detect trailing whitespace on lines INSIDE fenced code blocks in Markdown.

Stdlib only. Trailing whitespace inside a fenced code block is a high-signal
LLM defect: it survives into rendered `<pre>` blocks, breaks byte-for-byte
diffs, and corrupts copy-paste of shell snippets (e.g. invisible spaces at
end of a command). Outside fences, trailing whitespace is sometimes a
deliberate Markdown hard-line-break (two spaces) so we do NOT flag it here.

Scope:
  - Only lines strictly between an opening fence and its matching closing
    fence are checked.
  - The fence lines themselves are not checked.
  - Both backtick (```) and tilde (~~~) fences are supported. The closing
    fence must use the same marker character and be at least as long as
    the opening fence (CommonMark rule).

Usage:
    python3 detect.py FILE [FILE ...]

Exit codes:
    0  clean
    1  trailing whitespace found inside a fence
    2  usage / IO error
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

FENCE_RE = re.compile(r"^( {0,3})(`{3,}|~{3,})(.*)$")


def scan(path: Path) -> list[str]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"{path}: cannot read: {exc}", file=sys.stderr)
        return ["__io__"]

    lines = text.splitlines()
    findings: list[str] = []

    in_fence = False
    fence_char = ""
    fence_len = 0

    for idx, line in enumerate(lines, start=1):
        m = FENCE_RE.match(line)
        if m:
            marker = m.group(2)
            ch = marker[0]
            length = len(marker)
            if not in_fence:
                in_fence = True
                fence_char = ch
                fence_len = length
                continue
            # Currently inside a fence: this could be the closer.
            # Closer must be same char, length >= opener length, and (per
            # CommonMark) carry no info string. We accept trailing spaces
            # on the closer for tolerance.
            if ch == fence_char and length >= fence_len and m.group(3).strip() == "":
                in_fence = False
                fence_char = ""
                fence_len = 0
                continue
            # Otherwise, treat as content line inside the fence and fall
            # through to the trailing-whitespace check below.

        if in_fence:
            # Check trailing whitespace (space or tab).
            stripped = line.rstrip(" \t")
            if stripped != line:
                trailing = line[len(stripped):]
                kinds = []
                if " " in trailing:
                    kinds.append(f"{trailing.count(' ')} space(s)")
                if "\t" in trailing:
                    kinds.append(f"{trailing.count(chr(9))} tab(s)")
                findings.append(
                    f"{path}:{idx}:{len(stripped) + 1}: trailing whitespace inside fenced code block ({', '.join(kinds)})"
                )

    if in_fence:
        findings.append(
            f"{path}:EOF: file ended while inside an unclosed fenced code block"
        )

    return findings


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: detect.py FILE [FILE ...]", file=sys.stderr)
        return 2
    rc = 0
    for arg in argv[1:]:
        results = scan(Path(arg))
        if results == ["__io__"]:
            rc = max(rc, 2)
            continue
        for line in results:
            print(line)
        if results:
            rc = max(rc, 1)
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv))
