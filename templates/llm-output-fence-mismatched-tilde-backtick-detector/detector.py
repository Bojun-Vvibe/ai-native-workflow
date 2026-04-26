#!/usr/bin/env python3
"""Detect mismatched fence kinds: opens with ``` but closes with ~~~ (or vice versa).

Per CommonMark, a fenced code block opened with N backticks must be
closed by a line of >= N backticks; tildes do not close a backtick
fence and vice versa. LLMs frequently emit:

    ```python
    print("hi")
    ~~~

The `~~~` is treated as plain text inside the still-open backtick
fence, so the fence runs to end-of-document and silently swallows the
rest of the file as code.

This detector tracks open fences and flags any line that *looks* like
a closing fence of the wrong kind appearing before a valid same-kind
close. It also flags fences left open at EOF.

Pure stdlib. Single pass. Exit 0 = clean, 1 = findings, 2 = usage.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

OPEN_RE = re.compile(r"^(\s{0,3})(`{3,}|~{3,})([^`\n]*)$")
# A line that is *only* fence characters (>=3) of one kind, with optional
# leading indent and trailing whitespace.
CLOSE_BACKTICK_RE = re.compile(r"^\s{0,3}`{3,}\s*$")
CLOSE_TILDE_RE = re.compile(r"^\s{0,3}~{3,}\s*$")


def scan(path: Path) -> list[tuple[int, str]]:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    findings: list[tuple[int, str]] = []

    open_kind: str | None = None  # '`' or '~'
    open_len: int = 0
    open_lineno: int = 0

    for lineno, line in enumerate(lines, 1):
        if open_kind is None:
            m = OPEN_RE.match(line)
            if m:
                marker = m.group(2)
                open_kind = marker[0]
                open_len = len(marker)
                open_lineno = lineno
            continue

        # Inside an open fence — look for a closer
        stripped = line.strip()
        if not stripped:
            continue

        same_kind = (open_kind == "`" and CLOSE_BACKTICK_RE.match(line)) or \
                    (open_kind == "~" and CLOSE_TILDE_RE.match(line))
        wrong_kind = (open_kind == "`" and CLOSE_TILDE_RE.match(line)) or \
                     (open_kind == "~" and CLOSE_BACKTICK_RE.match(line))

        if same_kind:
            # Validate length
            run = len(stripped) - len(stripped.lstrip(open_kind))
            run = sum(1 for c in stripped if c == open_kind)
            if run >= open_len:
                open_kind = None
                open_len = 0
                open_lineno = 0
            # else: too-short closer — treated as content, keep open
        elif wrong_kind:
            other = "~~~" if open_kind == "`" else "```"
            opener = open_kind * open_len
            findings.append((
                lineno,
                f"line looks like a closing fence '{other}' but the open fence "
                f"on line {open_lineno} is '{opener}' — kinds must match",
            ))
            # Treat as a (forgiving) close so we don't cascade-flag the rest
            open_kind = None
            open_len = 0
            open_lineno = 0

    if open_kind is not None:
        opener = open_kind * open_len
        findings.append((
            open_lineno,
            f"code fence '{opener}' opened here is never closed before EOF",
        ))

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
