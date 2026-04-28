#!/usr/bin/env python3
"""Detect Java empty `catch` blocks (the "swallowed exception" anti-pattern).

Usage:
    python3 detect.py <file_or_dir> [<file_or_dir> ...]

Exit code 1 if any findings, 0 otherwise. python3 stdlib only.

An empty `catch` block silently discards the exception. The caller has
no signal that anything went wrong, the stack trace is gone, and the
program continues in an unknown state. The legitimate cases (genuinely
ignorable exceptions) are rare enough that they should be marked with a
comment explaining *why* — so a `catch (Foo e) { /* explanation */ }`
counts as a real comment, not "empty".

LLMs emit empty catches frequently because:

- The training corpus is full of tutorial code that ignores exceptions
  to keep the snippet short.
- The model "fixes" a checked-exception compile error by wrapping the
  call in `try { ... } catch (Exception ignored) {}` instead of fixing
  the actual cause.
- The model treats `try/catch` as a syntactic ritual rather than a
  control-flow construct.

This detector flags a `catch (...) { }` whose body contains no
statements *and* no comments. A body with any code or any comment is
not flagged.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


def strip_strings_only(text: str) -> str:
    """Blank out Java string and char literals while preserving comments
    (we need the comments later to decide whether a catch is *really*
    empty). Preserve line numbers and length.
    """
    out = []
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        nxt = text[i + 1] if i + 1 < n else ""
        # Text block """ ... """
        if ch == '"' and nxt == '"' and i + 2 < n and text[i + 2] == '"':
            out.append('"""')
            i += 3
            while i < n:
                if (
                    text[i] == '"'
                    and i + 2 < n
                    and text[i + 1] == '"'
                    and text[i + 2] == '"'
                ):
                    out.append('"""')
                    i += 3
                    break
                c = text[i]
                out.append("\n" if c == "\n" else " ")
                i += 1
            continue
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
                out.append(" ")
                i += 1
            continue
        out.append(ch)
        i += 1
    return "".join(out)


RE_CATCH = re.compile(r"\bcatch\s*\(([^)]*)\)\s*\{")


def find_block_end(text: str, open_brace_idx: int) -> int:
    """Return index just past the matching `}` for the `{` at open_brace_idx.

    Comments and strings are ignored (string literals were already
    blanked, but comments are still present)."""
    depth = 1
    i = open_brace_idx + 1
    n = len(text)
    while i < n and depth > 0:
        ch = text[i]
        nxt = text[i + 1] if i + 1 < n else ""
        if ch == "/" and nxt == "/":
            j = text.find("\n", i)
            i = n if j == -1 else j
            continue
        if ch == "/" and nxt == "*":
            j = text.find("*/", i + 2)
            i = n if j == -1 else j + 2
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return -1


def body_is_empty(body: str) -> bool:
    """True iff body contains no code AND no comments — only whitespace."""
    i = 0
    n = len(body)
    while i < n:
        ch = body[i]
        nxt = body[i + 1] if i + 1 < n else ""
        if ch.isspace():
            i += 1
            continue
        if ch == "/" and nxt == "/":
            # any line comment counts as documentation -> not empty
            return False
        if ch == "/" and nxt == "*":
            return False
        # any other character is code
        return False
    return True


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
    scrub = strip_strings_only(raw)
    raw_lines = raw.splitlines()
    for m in RE_CATCH.finditer(scrub):
        brace_idx = m.end() - 1  # position of `{`
        end = find_block_end(scrub, brace_idx)
        if end < 0:
            continue
        body = scrub[brace_idx + 1 : end - 1]
        if body_is_empty(body):
            line, col = line_col_of(scrub, m.start())
            snippet = (
                raw_lines[line - 1].strip() if line - 1 < len(raw_lines) else ""
            )
            findings.append((path, line, col, "empty-catch", snippet))
    return findings


def iter_targets(roots: list[str]):
    for r in roots:
        p = Path(r)
        if p.is_dir():
            for sub in sorted(p.rglob("*")):
                if sub.is_file() and sub.suffix == ".java":
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
            print(f"{f_path}:{line}:{col}: {kind} \u2014 {snippet}")
            total += 1
    print(f"# {total} finding(s)")
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
