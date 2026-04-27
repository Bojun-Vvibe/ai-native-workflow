#!/usr/bin/env python3
"""Detect empty cells in GFM markdown tables.

Usage: detect.py <path-to-markdown>
Exits 0 (clean), 1 (findings), or 2 (usage error).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

SEP_CELL = re.compile(r"^:?-+:?$")


def split_row(line: str) -> list[tuple[int, str]]:
    """Return (column-index-1based, raw-cell-text) for a pipe-delimited row.

    The leading/trailing fragments outside the outer pipes are dropped if they
    are whitespace only (the common GFM case `| a | b |`). Otherwise they are
    kept so we still flag genuinely broken rows.
    """
    # Don't split on escaped pipes (\|).
    # Replace escaped pipes with a sentinel, split, then restore.
    sentinel = "\x00ESCPIPE\x00"
    work = line.replace("\\|", sentinel)
    parts = work.split("|")
    # Strip outer empties (the convention `| a | b |` -> ['', ' a ', ' b ', '']).
    if parts and parts[0].strip() == "":
        parts = parts[1:]
    if parts and parts[-1].strip() == "":
        parts = parts[:-1]
    return [(i + 1, p.replace(sentinel, "|")) for i, p in enumerate(parts)]


def is_table_row(line: str) -> bool:
    stripped = line.lstrip()
    if not stripped.startswith("|"):
        return False
    # Need at least two pipes to qualify.
    return stripped.count("|") >= 2


def is_separator_row(cells: list[tuple[int, str]]) -> bool:
    if not cells:
        return False
    for _, c in cells:
        if not SEP_CELL.match(c.strip()):
            return False
    return True


def detect(path: Path) -> int:
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        print(f"error: {path} is not valid UTF-8", file=sys.stderr)
        return 2
    lines = text.splitlines()
    findings = 0
    i = 0
    while i < len(lines):
        line = lines[i]
        if not is_table_row(line):
            i += 1
            continue
        # Possible header row. Look ahead for separator row.
        header_cells = split_row(line)
        sep_idx = i + 1
        if sep_idx < len(lines) and is_table_row(lines[sep_idx]):
            sep_cells = split_row(lines[sep_idx])
            if is_separator_row(sep_cells):
                # Confirmed table. Check header.
                _check_row(path, i + 1, header_cells, "header", findings_inc=lambda: None)
                findings += _count_empty(header_cells)
                _emit(path, i + 1, header_cells, "header", line)
                # Check separator (all cells must be non-empty by definition of
                # being a sep row, but extra-defensive).
                findings += _count_empty(sep_cells)
                _emit(path, sep_idx + 1, sep_cells, "separator", lines[sep_idx])
                # Body rows.
                j = sep_idx + 1
                while j < len(lines) and is_table_row(lines[j]):
                    body_cells = split_row(lines[j])
                    findings += _count_empty(body_cells)
                    _emit(path, j + 1, body_cells, "body", lines[j])
                    j += 1
                i = j
                continue
        i += 1
    print(f"findings: {findings}", file=sys.stderr)
    return 1 if findings else 0


def _count_empty(cells: list[tuple[int, str]]) -> int:
    return sum(1 for _, c in cells if c.strip() == "")


def _emit(path: Path, line_no: int, cells: list[tuple[int, str]], kind: str, raw: str) -> None:
    # Compute approximate column for each empty cell by walking the raw line.
    pipe_positions = [idx for idx, ch in enumerate(raw) if ch == "|"]
    # Skip leading pipe if present.
    leading_offset = 1 if raw.lstrip().startswith("|") else 0
    for col_idx, cell in cells:
        if cell.strip() != "":
            continue
        # Pick the pipe just before this cell. col_idx is 1-based.
        # If there's a leading outer pipe, the cell at col_idx sits between
        # pipe[col_idx-1] and pipe[col_idx].
        try:
            col_pos = pipe_positions[col_idx - 1 + leading_offset - 1] + 2
        except IndexError:
            col_pos = 1
        print(f"{path}:{line_no}:{col_pos} empty cell in {kind} row col={col_idx}")


def _check_row(*_args, **_kwargs) -> None:  # placeholder kept for clarity
    return


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
