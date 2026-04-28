#!/usr/bin/env python3
"""Detect PHP loose-equality (`==` / `!=` / `<>`) usage.

Usage:
    python3 detect.py <file_or_dir> [<file_or_dir> ...]

Exit code 1 if any findings, 0 otherwise. python3 stdlib only.

PHP's loose-equality operators (`==`, `!=`, `<>`) perform type juggling
that produces famous foot-guns:

    0 == "abc"        // true on PHP < 8
    "1" == "01"       // true
    "10" == "1e1"     // true
    100 == "1e2"      // true
    null == false     // true
    [] == false       // true

Strict comparison (`===`, `!==`) compares both type and value and is
the recommended default for production PHP. PSR / modern PHP style
guides and tools like PHPStan, Psalm, and PHP_CodeSniffer all flag
loose equality.

LLMs produce `==` / `!=` in PHP because:

- Their training corpus contains a large amount of legacy PHP 5 code
  written before strict comparison was idiomatic.
- They cross-contaminate from JavaScript, where `==` is similarly
  discouraged but still common in older snippets.
- "Equal" is the obvious one-token completion; reaching for `===`
  requires the model to remember PHP-specific style.

This detector flags `==`, `!=`, and `<>` outside of comments and
strings. It deliberately does NOT flag `===` or `!==`.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


def strip_comments_and_strings(text: str) -> str:
    """Blank out PHP comments and string literals while preserving line
    numbers. Handles `//`, `#`, `/* ... */`, single-quoted, and
    double-quoted strings (with backslash escapes). Heredoc/nowdoc are
    treated conservatively by blanking the entire line range."""
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
        # line comment //
        if ch == "/" and nxt == "/":
            j = text.find("\n", i)
            if j == -1:
                out.append(" " * (n - i))
                break
            out.append(" " * (j - i))
            i = j
            continue
        # line comment #
        if ch == "#":
            j = text.find("\n", i)
            if j == -1:
                out.append(" " * (n - i))
                break
            out.append(" " * (j - i))
            i = j
            continue
        # heredoc / nowdoc <<<
        if ch == "<" and text[i : i + 3] == "<<<":
            # find end of label line
            eol = text.find("\n", i)
            if eol == -1:
                for c in text[i:]:
                    out.append("\n" if c == "\n" else " ")
                break
            header = text[i:eol]
            # extract label (strip optional quotes)
            m = re.match(r"<<<\s*[\"']?([A-Za-z_][\w]*)[\"']?", header)
            if not m:
                out.append(ch)
                i += 1
                continue
            label = m.group(1)
            # blank header
            for c in header:
                out.append(" ")
            out.append("\n")
            i = eol + 1
            # find terminator: a line whose first non-space token is label
            term_re = re.compile(r"^[ \t]*" + re.escape(label) + r"\b")
            # walk line by line
            while i < n:
                nl = text.find("\n", i)
                segment = text[i : nl if nl != -1 else n]
                if term_re.match(segment):
                    out.append(segment)
                    if nl != -1:
                        out.append("\n")
                        i = nl + 1
                    else:
                        i = n
                    break
                for c in segment:
                    out.append(" ")
                if nl != -1:
                    out.append("\n")
                    i = nl + 1
                else:
                    i = n
                    break
            continue
        # double-quoted string
        if ch == '"':
            out.append('"')
            i += 1
            while i < n:
                c = text[i]
                if c == "\\" and i + 1 < n:
                    out.append("  ")
                    i += 2
                    continue
                if c == '"':
                    out.append('"')
                    i += 1
                    break
                out.append("\n" if c == "\n" else " ")
                i += 1
            continue
        # single-quoted string
        if ch == "'":
            out.append("'")
            i += 1
            while i < n:
                c = text[i]
                if c == "\\" and i + 1 < n:
                    out.append("  ")
                    i += 2
                    continue
                if c == "'":
                    out.append("'")
                    i += 1
                    break
                out.append("\n" if c == "\n" else " ")
                i += 1
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def find_loose_equality(scrub: str):
    """Yield (offset, kind, match_text) for each loose-equality op.

    Kinds: `eq` (==), `ne` (!=), `angle-ne` (<>).
    Excludes `===`, `!==`, `==>`, `=>`, `<=`, `>=`, `<=>`.
    """
    n = len(scrub)
    i = 0
    while i < n:
        ch = scrub[i]
        # `==` but not `===` and not `=>`
        if ch == "=" and i + 1 < n and scrub[i + 1] == "=":
            # third char
            third = scrub[i + 2] if i + 2 < n else ""
            if third == "=":
                i += 3
                continue
            # also skip `==>` (rare custom operators / arrows in attrs);
            # treat as loose `==` followed by `>` — still loose. So flag.
            yield i, "eq", "=="
            i += 2
            continue
        # `!=` but not `!==`
        if ch == "!" and i + 1 < n and scrub[i + 1] == "=":
            third = scrub[i + 2] if i + 2 < n else ""
            if third == "=":
                i += 3
                continue
            yield i, "ne", "!="
            i += 2
            continue
        # `<>` but not `<=>` (spaceship) and not `<=`
        if ch == "<" and i + 1 < n and scrub[i + 1] == ">":
            yield i, "angle-ne", "<>"
            i += 2
            continue
        i += 1


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
    for off, kind, _ in find_loose_equality(scrub):
        line, col = line_col_of(scrub, off)
        snippet = raw_lines[line - 1].strip() if line - 1 < len(raw_lines) else ""
        findings.append((path, line, col, kind, snippet))
    return findings


def iter_targets(roots: list[str]):
    for r in roots:
        p = Path(r)
        if p.is_dir():
            for sub in sorted(p.rglob("*")):
                if sub.is_file() and sub.suffix in (".php", ".phtml", ".inc"):
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
