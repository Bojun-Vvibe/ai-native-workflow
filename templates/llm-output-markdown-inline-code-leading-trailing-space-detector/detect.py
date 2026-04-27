#!/usr/bin/env python3
"""Detect unnecessary leading/trailing whitespace inside markdown inline-code.

Usage: detect.py <path-to-markdown>
Exit codes: 0 clean, 1 findings, 2 usage/IO error.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

# Match opening run of backticks; we'll find the matching closing run manually.
RUN = re.compile(r"`+")
FENCE = re.compile(r"^\s{0,3}(```+|~~~+)")


def find_spans(line: str) -> list[tuple[int, int, str]]:
    """Return list of (start_col_0based, end_col_0based, content) for inline
    code spans on a single line. Skips backtick-escaped sequences (\\`)."""
    spans: list[tuple[int, int, str]] = []
    i = 0
    n = len(line)
    while i < n:
        # Honor backslash escapes for backticks.
        if line[i] == "\\" and i + 1 < n and line[i + 1] == "`":
            i += 2
            continue
        if line[i] != "`":
            i += 1
            continue
        # Count the run of backticks.
        j = i
        while j < n and line[j] == "`":
            j += 1
        run_len = j - i
        # Look for matching closing run of EXACTLY run_len backticks.
        k = j
        while k < n:
            if line[k] == "\\" and k + 1 < n and line[k + 1] == "`":
                k += 2
                continue
            if line[k] != "`":
                k += 1
                continue
            m = k
            while m < n and line[m] == "`":
                m += 1
            close_len = m - k
            if close_len == run_len:
                content = line[j:k]
                spans.append((i, m, content))
                i = m
                break
            else:
                k = m
        else:
            # No closing run found; skip past the opening.
            i = j
    return spans


def detect(path: Path) -> int:
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        print(f"error: {path} is not valid UTF-8", file=sys.stderr)
        return 2
    findings = 0
    in_fence = False
    fence_marker = ""
    for line_no, line in enumerate(text.splitlines(), start=1):
        m = FENCE.match(line)
        if m:
            marker = m.group(1)[0] * 3  # ``` or ~~~
            if not in_fence:
                in_fence = True
                fence_marker = marker
            elif line.lstrip().startswith(fence_marker):
                in_fence = False
                fence_marker = ""
            continue
        if in_fence:
            continue
        for start, _end, content in find_spans(line):
            if not content:
                continue
            leading_space = content[0] == " "
            trailing_space = content[-1] == " "
            # GFM exception: a single leading/trailing space is permitted ONLY
            # when the content itself begins (resp. ends) with a backtick.
            if leading_space and len(content) > 1 and content[1] == "`":
                leading_space = False
            if trailing_space and len(content) > 1 and content[-2] == "`":
                trailing_space = False
            if not (leading_space or trailing_space):
                continue
            kind = (
                "both"
                if leading_space and trailing_space
                else ("leading" if leading_space else "trailing")
            )
            findings += 1
            col = start + 1
            print(
                f"{path}:{line_no}:{col} {kind} whitespace inside inline code: {content!r}"
            )
    print(f"findings: {findings}", file=sys.stderr)
    return 1 if findings else 0


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: detect.py <path-to-markdown>", file=sys.stderr)
        return 2
    path = Path(argv[1])
    if not path.is_file():
        print(f"error: {path} not found", file=sys.stderr)
        return 2
    return detect(path)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
