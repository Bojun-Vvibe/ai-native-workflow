#!/usr/bin/env python3
"""Detect GitHub-flavored markdown tables whose body rows have a
column count that does not match the header row's column count.

A GFM table looks like:

    | h1 | h2 | h3 |
    | -- | -- | -- |
    | a  | b  | c  |
    | d  | e  |       <-- 2 cells, mismatch with header (3)
    | f  | g  | h | i  <-- 4 cells, mismatch

The header column count is defined by the header row (the line
immediately above the separator row). Every body row in the same
contiguous table block must have the same number of cells as the
header. Trailing empty cells produced by an outer trailing pipe are
counted normally (GFM treats `| a | b |` as 2 cells).

Code-fence aware: tables inside fenced code blocks (``` or ~~~) are
ignored.

Exit codes:
  0 = no findings
  1 = findings printed to stdout
  2 = usage error
"""
from __future__ import annotations

import re
import sys

FENCE_RE = re.compile(r"^\s*(```+|~~~+)")
# Separator cell: optional leading/trailing colon around >=2 dashes
SEP_CELL_RE = re.compile(r"^\s*:?-{2,}:?\s*$")


def split_cells(line: str) -> list[str]:
    """Split a GFM table row into cells. Strips a single outer pipe
    on each side if present. Does not handle backslash-escaped pipes
    perfectly, but treats `\\|` as a literal (not a separator).
    """
    s = line.rstrip("\n")
    # Find all unescaped pipes
    cells: list[str] = []
    buf = []
    i = 0
    while i < len(s):
        ch = s[i]
        if ch == "\\" and i + 1 < len(s) and s[i + 1] == "|":
            buf.append("|")
            i += 2
            continue
        if ch == "|":
            cells.append("".join(buf))
            buf = []
            i += 1
            continue
        buf.append(ch)
        i += 1
    cells.append("".join(buf))
    # Strip a single empty leading/trailing cell from outer pipes.
    if cells and cells[0].strip() == "":
        cells = cells[1:]
    if cells and cells[-1].strip() == "":
        cells = cells[:-1]
    return cells


def is_separator_row(line: str) -> bool:
    cells = split_cells(line)
    if len(cells) < 1:
        return False
    return all(SEP_CELL_RE.match(c) for c in cells)


def looks_like_table_row(line: str) -> bool:
    s = line.strip()
    if not s:
        return False
    # Need at least one unescaped pipe.
    in_esc = False
    for ch in s:
        if in_esc:
            in_esc = False
            continue
        if ch == "\\":
            in_esc = True
            continue
        if ch == "|":
            return True
    return False


def scan(text: str):
    in_fence = False
    findings = []
    lines = text.splitlines()
    i = 0
    n = len(lines)
    while i < n:
        raw = lines[i]
        if FENCE_RE.match(raw):
            in_fence = not in_fence
            i += 1
            continue
        if in_fence:
            i += 1
            continue
        # Look for header: a row immediately followed by a separator row.
        if (
            looks_like_table_row(raw)
            and i + 1 < n
            and looks_like_table_row(lines[i + 1])
            and is_separator_row(lines[i + 1])
            and not is_separator_row(raw)
        ):
            header_cells = split_cells(raw)
            sep_cells = split_cells(lines[i + 1])
            expected = len(header_cells)
            # Optional: also flag separator vs header mismatch.
            if len(sep_cells) != expected:
                findings.append(
                    (
                        i + 2,
                        f"separator row has {len(sep_cells)} cells, header has {expected}",
                        lines[i + 1],
                    )
                )
            j = i + 2
            while j < n:
                rj = lines[j]
                if FENCE_RE.match(rj):
                    in_fence = not in_fence
                    break
                if not looks_like_table_row(rj):
                    break
                if is_separator_row(rj):
                    # A second separator inside a table block: stop here.
                    break
                body_cells = split_cells(rj)
                if len(body_cells) != expected:
                    findings.append(
                        (
                            j + 1,
                            f"body row has {len(body_cells)} cells, header has {expected}",
                            rj,
                        )
                    )
                j += 1
            i = j
            continue
        i += 1
    return findings


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(f"usage: {argv[0]} <file.md>", file=sys.stderr)
        return 2
    path = argv[1]
    try:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
    except OSError as exc:
        print(f"error reading {path}: {exc}", file=sys.stderr)
        return 2
    findings = scan(text)
    for line_no, msg, raw in findings:
        print(f"{path}:{line_no}: {msg}: {raw.rstrip()}")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
