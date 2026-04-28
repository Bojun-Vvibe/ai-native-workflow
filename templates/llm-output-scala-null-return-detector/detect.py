#!/usr/bin/env python3
"""Detect Scala methods that explicitly return `null`.

Usage:
    python3 detect.py <file_or_dir> [<file_or_dir> ...]

Exit code 1 if any findings, 0 otherwise. python3 stdlib only.

Scala has `Option[T]` (`Some(x)` / `None`) precisely so that absence is
encoded in the type system. Returning a bare `null` from Scala defeats
the type system, makes downstream callers vulnerable to
`NullPointerException`, and is widely considered an anti-pattern.

LLMs frequently emit `return null` or `null` as the last expression in a
Scala method because they pattern-match from Java training data. This
detector flags any function/method body whose last expression is the
identifier `null` or that contains a `return null` statement.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

# Method declaration:  def name(...): T = ... { ... } OR def name(...) = ...
RE_DEF = re.compile(r"\bdef\s+([A-Za-z_][\w]*)\b")
RE_RETURN_NULL = re.compile(r"\breturn\s+null\b")
RE_LAST_NULL = re.compile(r"(?:^|[\s;{(=,])null\s*$")


def strip_comments_and_strings(text: str) -> str:
    """Blank out // and /* */ comments and string/char/triple-quoted
    string literals so regex matching does not fire inside them.
    Preserve line numbers."""
    out = []
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        nxt = text[i + 1] if i + 1 < n else ""
        nxt2 = text[i + 2] if i + 2 < n else ""
        # block comment
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
        # line comment
        if ch == "/" and nxt == "/":
            j = text.find("\n", i)
            if j == -1:
                out.append(" " * (n - i))
                break
            out.append(" " * (j - i))
            i = j
            continue
        # triple-quoted """..."""
        if ch == '"' and nxt == '"' and nxt2 == '"':
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
                out.append("\n" if text[i] == "\n" else " ")
                i += 1
            continue
        # plain string
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
        # char literal '...'
        if ch == "'":
            # Scala also uses ' for symbols (deprecated) and char literals.
            # Treat as char if next-next is '.
            out.append("'")
            i += 1
            steps = 0
            while i < n and steps < 4:
                c = text[i]
                if c == "\\" and i + 1 < n:
                    out.append("  ")
                    i += 2
                    steps += 1
                    continue
                if c == "'":
                    out.append("'")
                    i += 1
                    break
                out.append(" ")
                i += 1
                steps += 1
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def find_method_bodies(scrub: str):
    """Yield (body_text, body_start_offset, name) for each `def` whose
    body is a brace block `{ ... }`. Heuristic: after `def name(...)`,
    skip past the parameter lists and optional return type, then find
    `=` followed by `{`, capture matching block.
    """
    n = len(scrub)
    for m in RE_DEF.finditer(scrub):
        name = m.group(1)
        i = m.end()
        # Skip type params [...]
        if i < n and scrub[i] == "[":
            d = 0
            while i < n:
                if scrub[i] == "[":
                    d += 1
                elif scrub[i] == "]":
                    d -= 1
                    if d == 0:
                        i += 1
                        break
                i += 1
        # Skip parameter lists (one or more `(...)`).
        while True:
            while i < n and scrub[i] in " \t\r\n":
                i += 1
            if i < n and scrub[i] == "(":
                d = 0
                while i < n:
                    if scrub[i] == "(":
                        d += 1
                    elif scrub[i] == ")":
                        d -= 1
                        if d == 0:
                            i += 1
                            break
                    i += 1
            else:
                break
        # Skip optional `: ReturnType`. Stop at `=` or `{` or newline.
        while i < n and scrub[i] != "=" and scrub[i] != "{" and scrub[i] != "\n":
            i += 1
        if i >= n:
            continue
        if scrub[i] == "\n":
            continue
        if scrub[i] == "=":
            i += 1
            while i < n and scrub[i] in " \t\r\n":
                i += 1
        if i < n and scrub[i] == "{":
            d = 0
            body_start = i
            while i < n:
                if scrub[i] == "{":
                    d += 1
                elif scrub[i] == "}":
                    d -= 1
                    if d == 0:
                        yield scrub[body_start : i + 1], body_start, name
                        break
                i += 1


def line_col_of(text: str, offset: int) -> tuple[int, int]:
    line = text.count("\n", 0, offset) + 1
    last_nl = text.rfind("\n", 0, offset)
    col = offset - last_nl
    return line, col


def last_significant_token(body: str) -> tuple[str, int] | None:
    """Return (token, offset_in_body) for the last non-comment,
    non-whitespace identifier-or-literal token before the closing brace.
    Body includes the outer braces.
    """
    # trim trailing brace
    if not body.endswith("}"):
        return None
    inner = body[1:-1]
    # walk from the end, skipping whitespace
    j = len(inner) - 1
    while j >= 0 and inner[j] in " \t\r\n;":
        j -= 1
    if j < 0:
        return None
    end = j + 1
    # walk back while ident/word char
    start = end
    while start > 0 and (inner[start - 1].isalnum() or inner[start - 1] == "_"):
        start -= 1
    if start == end:
        return None
    token = inner[start:end]
    return token, start + 1  # +1 for the leading `{`


def scan_file(path: Path) -> list[tuple[Path, int, int, str, str]]:
    findings: list[tuple[Path, int, int, str, str]] = []
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return findings
    scrub = strip_comments_and_strings(raw)
    raw_lines = raw.splitlines()
    for body, body_off, name in find_method_bodies(scrub):
        # 1) explicit `return null`
        for m in RE_RETURN_NULL.finditer(body):
            abs_off = body_off + m.start()
            line, col = line_col_of(scrub, abs_off)
            snippet = (
                raw_lines[line - 1].strip() if line - 1 < len(raw_lines) else ""
            )
            findings.append((path, line, col, "return-null", snippet))
        # 2) last expression is `null`
        last = last_significant_token(body)
        if last and last[0] == "null":
            abs_off = body_off + last[1]
            line, col = line_col_of(scrub, abs_off)
            snippet = (
                raw_lines[line - 1].strip() if line - 1 < len(raw_lines) else ""
            )
            findings.append((path, line, col, "trailing-null", snippet))
    return findings


def iter_targets(roots: list[str]):
    for r in roots:
        p = Path(r)
        if p.is_dir():
            for sub in sorted(p.rglob("*")):
                if sub.is_file() and sub.suffix in (".scala", ".sc"):
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
