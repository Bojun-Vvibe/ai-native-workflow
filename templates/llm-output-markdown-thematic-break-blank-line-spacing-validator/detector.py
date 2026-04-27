#!/usr/bin/env python3
"""Validate blank-line spacing around markdown thematic breaks.

A thematic break in CommonMark is a line of 3+ matching `-`, `*`, or `_`
characters (optionally separated by spaces/tabs, optionally indented up to
3 spaces). To render reliably it must be surrounded by blank lines (or the
document edge); otherwise renderers may treat it as a Setext heading
underline or as plain text.

Exit code: 0 if no findings, 1 otherwise.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# After up to 3 leading spaces, 3+ of the same marker, possibly with
# interior spaces/tabs, then optional trailing spaces, end of line.
_RULE = re.compile(r"^ {0,3}([-*_])(?:[ \t]*\1){2,}[ \t]*$")


def _is_thematic_break(line: str) -> bool:
    return bool(_RULE.match(line))


def _is_blank(line: str | None) -> bool:
    return line is None or line.strip() == ""


def _is_inside_fenced_code(lines: list[str], idx: int) -> bool:
    """Cheap fence tracker: count opening ``` / ~~~ before idx."""
    open_fence: str | None = None
    for i in range(idx):
        stripped = lines[i].lstrip()
        if open_fence is None:
            if stripped.startswith("```") or stripped.startswith("~~~"):
                open_fence = stripped[:3]
        else:
            if stripped.startswith(open_fence):
                open_fence = None
    return open_fence is not None


def validate(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    lines = text.split("\n")
    findings: list[str] = []
    for i, line in enumerate(lines):
        if not _is_thematic_break(line):
            continue
        if _is_inside_fenced_code(lines, i):
            continue
        before = lines[i - 1] if i - 1 >= 0 else None
        after = lines[i + 1] if i + 1 < len(lines) else None
        if not _is_blank(before):
            findings.append(
                f"{path}:{i + 1}: thematic break missing blank line before"
            )
        if not _is_blank(after):
            findings.append(
                f"{path}:{i + 1}: thematic break missing blank line after"
            )
    return findings


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: detector.py FILE", file=sys.stderr)
        return 2
    findings = validate(Path(argv[1]))
    for f in findings:
        print(f)
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
