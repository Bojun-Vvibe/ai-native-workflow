#!/usr/bin/env python3
"""Detect unclosed HTML comments (`<!--` without matching `-->`) in Markdown.

Stdlib only. Code-fence and inline-code aware: comments inside fenced code
blocks or inline `code spans` are intentionally ignored, since those are
documentation about HTML comments, not actual comments.

Usage:
    python3 detect.py FILE [FILE ...]

Exit codes:
    0  clean
    1  unclosed comment found
    2  usage / IO error
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

FENCE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
INLINE_CODE_RE = re.compile(r"`+[^`\n]*`+")


def strip_inline_code(line: str) -> str:
    return INLINE_CODE_RE.sub("", line)


def scan(path: Path) -> list[str]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"{path}: cannot read: {exc}", file=sys.stderr)
        return ["__io__"]

    lines = text.splitlines()
    findings: list[str] = []

    in_fence = False
    fence_marker = ""
    in_comment = False
    comment_start: tuple[int, int] = (0, 0)

    for idx, line in enumerate(lines, start=1):
        m = FENCE_RE.match(line)
        if m and not in_comment:
            marker = m.group(1)[0]
            if not in_fence:
                in_fence = True
                fence_marker = marker
            elif marker == fence_marker:
                in_fence = False
                fence_marker = ""
            continue
        if in_fence:
            continue

        scrubbed = strip_inline_code(line) if not in_comment else line
        col = 0
        while col < len(scrubbed):
            if not in_comment:
                start = scrubbed.find("<!--", col)
                if start < 0:
                    break
                in_comment = True
                comment_start = (idx, start + 1)
                col = start + 4
            else:
                end = scrubbed.find("-->", col)
                if end < 0:
                    # Comment continues past end-of-line; jump to next line.
                    col = len(scrubbed)
                else:
                    in_comment = False
                    col = end + 3
        # When the comment continues across the whole next line, the line has
        # no `-->` and we just keep scanning. We do NOT use stripped inline
        # code while inside an open comment (because everything is comment
        # content until `-->`).

    if in_comment:
        line_no, col_no = comment_start
        findings.append(
            f"{path}:{line_no}:{col_no}: unclosed HTML comment '<!--' (no '-->' before EOF)"
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
