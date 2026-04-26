#!/usr/bin/env python3
"""Detect ordered (numbered) markdown lists that unexpectedly restart at 1.

LLMs sometimes break a single conceptual list into multiple sub-lists
because they emit a non-list line in the middle, which silently splits
the list and restarts numbering at 1 in rendered output.

This detector flags any ordered-list block whose first marker is `1.`
when an immediately-prior ordered list (within `LOOKBACK_BLANK` blank
lines and no intervening heading / fence / hr) ended at marker > 1.

Exit code 0 = clean, 1 = findings.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

OL_RE = re.compile(r"^(\s{0,3})(\d+)([.)])\s+\S")
HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s")
FENCE_RE = re.compile(r"^\s*(```+|~~~+)")
HR_RE = re.compile(r"^\s{0,3}([-*_])(\s*\1){2,}\s*$")

LOOKBACK_BLANK = 2  # max blank lines between blocks to consider them adjacent


def scan(path: Path) -> list[tuple[int, str]]:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    findings: list[tuple[int, str]] = []

    in_fence = False
    # Track most recent ordered-list block: (last_lineno, last_marker_int, indent)
    last_block: tuple[int, int, int] | None = None
    blank_run = 0
    barrier_seen = False  # heading/hr between last list and current

    cur_block_indent: int | None = None
    cur_block_last_marker: int | None = None
    cur_block_first_lineno: int | None = None
    cur_block_first_marker: int | None = None

    def close_block():
        nonlocal last_block, cur_block_indent, cur_block_last_marker
        nonlocal cur_block_first_lineno, cur_block_first_marker
        if cur_block_first_lineno is not None:
            # Check restart condition against last_block
            if (
                last_block is not None
                and not barrier_seen
                and blank_run <= LOOKBACK_BLANK
                and cur_block_first_marker == 1
                and last_block[1] > 1
                and last_block[2] == cur_block_indent
            ):
                findings.append((
                    cur_block_first_lineno,
                    f"ordered list restarts at 1 (previous list ended at {last_block[1]} on line {last_block[0]})",
                ))
            last_block = (
                # last line of the just-closed block uses last_marker
                cur_block_first_lineno,  # we only need a representative
                cur_block_last_marker or 0,
                cur_block_indent or 0,
            )
        cur_block_indent = None
        cur_block_last_marker = None
        cur_block_first_lineno = None
        cur_block_first_marker = None

    for lineno, line in enumerate(lines, 1):
        if FENCE_RE.match(line):
            in_fence = not in_fence
            close_block()
            barrier_seen = True
            blank_run = 0
            continue
        if in_fence:
            continue

        if not line.strip():
            blank_run += 1
            # blank line ends the current ol block but doesn't reset last_block
            close_block()
            continue

        if HEADING_RE.match(line) or HR_RE.match(line):
            close_block()
            barrier_seen = True
            last_block = None
            blank_run = 0
            continue

        m = OL_RE.match(line)
        if m:
            indent = len(m.group(1))
            marker = int(m.group(2))
            if cur_block_first_lineno is None:
                cur_block_first_lineno = lineno
                cur_block_first_marker = marker
                cur_block_indent = indent
                cur_block_last_marker = marker
            else:
                if indent == cur_block_indent:
                    cur_block_last_marker = marker
                # nested or dedented: ignore for this simple scan
            blank_run = 0
            barrier_seen = False
        else:
            # Non-list, non-blank, non-barrier text: closes block but
            # since LLMs often break a list by dropping a stray line,
            # treat this as a soft barrier (still counts toward restart
            # detection). We do NOT set barrier_seen here.
            close_block()
            blank_run = 0

    close_block()
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
