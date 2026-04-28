#!/usr/bin/env python3
"""Detect C# `async void` methods (excluding event handlers).

Usage:
    python3 detect.py <file_or_dir> [<file_or_dir> ...]

Exit code 1 if any findings, 0 otherwise. python3 stdlib only.

`async void` is a footgun in C#: exceptions thrown inside an `async void`
method propagate to the SynchronizationContext and typically crash the
process; they cannot be awaited or caught by the caller. The only
legitimate use is event handlers (signature `(object sender, EventArgs
e)` or a derived `EventArgs`).

LLMs frequently emit `async void Foo()` when they mean `async Task Foo()`,
because the void return "looks simpler". This detector flags any
`async void` declaration whose parameter list does NOT match the event
handler shape.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

# Match: optional access modifiers, then `async ... void <Name>(<params>)`.
# We allow modifiers like public/private/protected/internal/static/
# override/virtual/sealed/new/extern/unsafe/partial in any order between
# `async` and `void`.
RE_ASYNC_VOID = re.compile(
    r"\b(?:public|private|protected|internal|static|override|virtual|"
    r"sealed|new|extern|unsafe|partial|\s)*"
    r"\basync\b"
    r"(?:\s+(?:public|private|protected|internal|static|override|virtual|"
    r"sealed|new|extern|unsafe|partial))*"
    r"\s+void\s+([A-Za-z_]\w*)\s*\(([^)]*)\)"
)

# Event handler signature: two parameters where the second's type ends in
# `EventArgs` (e.g. EventArgs, MouseEventArgs, RoutedEventArgs).
RE_EVENT_HANDLER = re.compile(
    r"^\s*[A-Za-z_][\w\.]*\s+[A-Za-z_]\w*\s*,"
    r"\s*(?:[A-Za-z_][\w\.]*\.)?\w*EventArgs\s+[A-Za-z_]\w*\s*$"
)


def strip_comments_and_strings(text: str) -> str:
    """Blank out // and /* */ comments and string/char/verbatim/interp
    literals so regex matching does not fire inside them. Preserve line
    numbers."""
    out = []
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        nxt = text[i + 1] if i + 1 < n else ""
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
        if ch == "/" and nxt == "/":
            j = text.find("\n", i)
            if j == -1:
                out.append(" " * (n - i))
                break
            out.append(" " * (j - i))
            i = j
            continue
        # @"..." verbatim string (doubled "" escapes ")
        if ch == "@" and nxt == '"':
            out.append("@\"")
            i += 2
            while i < n:
                c = text[i]
                if c == '"' and i + 1 < n and text[i + 1] == '"':
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
        # $"..." interpolated string (treat as regular string for blanking)
        if ch == "$" and nxt == '"':
            out.append("$\"")
            i += 2
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


def line_col_of(text: str, offset: int) -> tuple[int, int]:
    line = text.count("\n", 0, offset) + 1
    last_nl = text.rfind("\n", 0, offset)
    col = offset - last_nl
    return line, col


def is_event_handler_params(params: str) -> bool:
    return bool(RE_EVENT_HANDLER.match(params.strip()))


def scan_file(path: Path) -> list[tuple[Path, int, int, str, str]]:
    findings: list[tuple[Path, int, int, str, str]] = []
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return findings
    scrub = strip_comments_and_strings(raw)
    raw_lines = raw.splitlines()
    for m in RE_ASYNC_VOID.finditer(scrub):
        params = m.group(2)
        if is_event_handler_params(params):
            continue
        line, col = line_col_of(scrub, m.start())
        snippet = raw_lines[line - 1].strip() if line - 1 < len(raw_lines) else ""
        findings.append((path, line, col, "async-void", snippet))
    return findings


def iter_targets(roots: list[str]):
    for r in roots:
        p = Path(r)
        if p.is_dir():
            for sub in sorted(p.rglob("*")):
                if sub.is_file() and sub.suffix in (".cs",):
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
