#!/usr/bin/env python3
"""Detect `SELECT *` (and qualified variants like `SELECT t.*`) in SQL.

Usage:
    python3 detect.py <file_or_dir> [<file_or_dir> ...]

Exit code 1 if any findings, 0 otherwise. python3 stdlib only.

`SELECT *` in production queries is a well-known anti-pattern:

- Returns columns the caller does not actually need, wasting I/O and
  network bandwidth and defeating covering-index optimizations.
- Breaks downstream code silently when a column is added, removed,
  renamed, or has its type changed.
- Hides intent: a reader cannot tell from the query which columns the
  application actually depends on.
- Conflicts with `INSERT ... SELECT *` when the destination table
  schema drifts from the source.
- Pulls back blob/text/json columns into ORM hydration paths that the
  caller may not need.

Allowed contexts that the detector intentionally does NOT flag:

- `SELECT COUNT(*)`, `SELECT SUM(*)`, etc. — the `*` is an aggregate
  argument, not a column-list shortcut.
- `SELECT EXISTS (...)` and other expressions that do not start the
  column list with `*`.
- `*` inside string literals or comments.

LLMs emit `SELECT *` because it is the shortest, most token-cheap way
to satisfy a "give me the row" request, and because tutorials and
README snippets in the training data are dominated by `SELECT * FROM
table`. Production code should explicitly list the columns it needs.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


def strip_comments_and_strings(text: str) -> str:
    """Blank out SQL comments (-- and /* */) and string literals
    ('...' and "..." with doubled-quote escapes) while preserving line
    numbers."""
    out = []
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        nxt = text[i + 1] if i + 1 < n else ""
        # block comment /* ... */
        if ch == "/" and nxt == "*":
            j = text.find("*/", i + 2)
            if j == -1:
                for c in text[i:]:
                    out.append("\n" if c == "\n" else " ")
                break
            for c in text[i : j + 2]:
                out.append("\n" if c == "\n" else " ")
            i = j + 2
            continue
        # line comment -- ...
        if ch == "-" and nxt == "-":
            j = text.find("\n", i)
            if j == -1:
                out.append(" " * (n - i))
                break
            out.append(" " * (j - i))
            i = j
            continue
        # single-quoted string with '' escape
        if ch == "'":
            out.append("'")
            i += 1
            while i < n:
                c = text[i]
                if c == "'":
                    if i + 1 < n and text[i + 1] == "'":
                        out.append("  ")
                        i += 2
                        continue
                    out.append("'")
                    i += 1
                    break
                out.append("\n" if c == "\n" else " ")
                i += 1
            continue
        # double-quoted identifier/string with "" escape
        if ch == '"':
            out.append('"')
            i += 1
            while i < n:
                c = text[i]
                if c == '"':
                    if i + 1 < n and text[i + 1] == '"':
                        out.append("  ")
                        i += 2
                        continue
                    out.append('"')
                    i += 1
                    break
                out.append("\n" if c == "\n" else " ")
                i += 1
            continue
        # backtick identifier (MySQL)
        if ch == "`":
            out.append("`")
            i += 1
            while i < n:
                c = text[i]
                if c == "`":
                    out.append("`")
                    i += 1
                    break
                out.append("\n" if c == "\n" else " ")
                i += 1
            continue
        out.append(ch)
        i += 1
    return "".join(out)


# After SELECT (optionally followed by DISTINCT/ALL/TOP <n>), require
# the first non-trivial column-list token to be `*` or `<ident>.*`.
# Examples that match:
#   SELECT * FROM t
#   SELECT DISTINCT * FROM t
#   SELECT ALL * FROM t
#   SELECT TOP 10 * FROM t
#   SELECT t.* FROM t
#   SELECT u.*, o.id FROM ...
RE_SELECT = re.compile(
    r"(?is)\bSELECT\b"
    r"(?:\s+(?:DISTINCT|ALL))?"
    r"(?:\s+TOP\s+\d+)?"
    r"\s+"
    r"(?P<head>(?:[A-Za-z_][\w]*\s*\.\s*)?\*)"
    r"(?=\s*(?:,|\bFROM\b))"
)


def find_select_star(scrub: str):
    """Yield (offset, kind, matched_text) for each SELECT * variant."""
    for m in RE_SELECT.finditer(scrub):
        head = m.group("head").replace(" ", "")
        kind = "select-star" if head == "*" else "select-qualified-star"
        yield m.start("head"), kind, head


def line_col_of(text: str, offset: int) -> tuple[int, int]:
    line = text.count("\n", 0, offset) + 1
    last_nl = text.rfind("\n", 0, offset)
    col = offset - last_nl
    return line, col


def scan_file(path: Path) -> list[tuple[Path, int, int, str, str]]:
    findings: list[tuple[Path, int, int, str, str]] = []
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return findings
    scrub = strip_comments_and_strings(raw)
    raw_lines = raw.splitlines()
    for off, kind, _ in find_select_star(scrub):
        line, col = line_col_of(scrub, off)
        snippet = raw_lines[line - 1].strip() if line - 1 < len(raw_lines) else ""
        findings.append((path, line, col, kind, snippet))
    return findings


def iter_targets(roots: list[str]):
    for r in roots:
        p = Path(r)
        if p.is_dir():
            for sub in sorted(p.rglob("*")):
                if sub.is_file() and sub.suffix.lower() in (".sql", ".ddl", ".dml"):
                    yield sub
        elif p.is_file():
            yield p


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(f"usage: {argv[0]} <file_or_dir> [...]", file=sys.stderr)
        return 2
    total = 0
    for path in iter_targets(argv[1:]):
        for f_path, line, col, kind, snippet in scan_file(path):
            print(f"{f_path}:{line}:{col}: {kind} — {snippet}")
            total += 1
    print(f"# {total} finding(s)")
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
