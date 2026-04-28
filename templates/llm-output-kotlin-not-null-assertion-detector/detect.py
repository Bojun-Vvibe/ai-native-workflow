#!/usr/bin/env python3
"""Detect Kotlin not-null assertion (`!!`) usages in `.kt` / `.kts` files.

Usage:
    python3 detect.py <file_or_dir> [<file_or_dir> ...]

Exit code 1 if any findings, 0 otherwise. python3 stdlib only.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

# `!!` only when it follows an identifier-char, `)`, `]`, or `?` — i.e.
# something that could be an expression of nullable type. This avoids the
# double-prefix-not case `!!isReady`.
RE_BANG_BANG = re.compile(r"(?<=[\w\)\]\?])!!")


def _strip_strings_and_comment(line: str) -> str:
    """Blank out double-quoted string literals and any trailing `//` comment.
    Crude but enough for line-based linting."""
    out = []
    i = 0
    n = len(line)
    in_str = False
    while i < n:
        ch = line[i]
        if not in_str and ch == "/" and i + 1 < n and line[i + 1] == "/":
            break
        if ch == '"':
            in_str = not in_str
            out.append('"')
        elif in_str:
            if ch == "\\" and i + 1 < n:
                out.append("  ")
                i += 2
                continue
            out.append(" ")
        else:
            out.append(ch)
        i += 1
    return "".join(out)


def _strip_block_comments(text: str) -> str:
    """Replace `/* ... */` block comments with spaces (preserve line breaks)."""
    out = []
    i = 0
    n = len(text)
    while i < n:
        if i + 1 < n and text[i] == "/" and text[i + 1] == "*":
            j = text.find("*/", i + 2)
            if j == -1:
                out.append(" " * (n - i))
                break
            for ch in text[i:j + 2]:
                out.append("\n" if ch == "\n" else " ")
            i = j + 2
        else:
            out.append(text[i])
            i += 1
    return "".join(out)


def scan_file(path: Path) -> list[tuple[Path, int, int, str, str]]:
    findings: list[tuple[Path, int, int, str, str]] = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return findings
    text = _strip_block_comments(text)
    raw_lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    for lineno, line in enumerate(text.splitlines(), start=1):
        scrub = _strip_strings_and_comment(line)
        for m in RE_BANG_BANG.finditer(scrub):
            snippet = (
                raw_lines[lineno - 1].strip() if lineno - 1 < len(raw_lines) else ""
            )
            findings.append((path, lineno, m.start() + 1, "not-null-assert", snippet))
    return findings


def iter_targets(roots: list[str]):
    for r in roots:
        p = Path(r)
        if p.is_dir():
            for sub in sorted(list(p.rglob("*.kt")) + list(p.rglob("*.kts"))):
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
