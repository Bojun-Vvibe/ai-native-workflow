#!/usr/bin/env python3
"""Detect Dart `late` field declarations with no initializer.

Usage:
    python3 detect.py <file_or_dir> [<file_or_dir> ...]

Exit code 1 if any findings, 0 otherwise. python3 stdlib only.

`late` in Dart defers null-safety checks from compile time to *first
read*. A `late` variable without an initializer says: "trust me, I will
assign this before anyone reads it." If that promise is wrong, the
program throws `LateInitializationError` at runtime — exactly the kind
of NullPointerException-shaped failure that null safety was supposed
to eliminate.

Legitimate uses do exist (DI containers, lazy circular references) but
they should be rare and deliberate. The shape this detector flags is:

    late <Type> name;            // no initializer
    late final <Type> name;      // no initializer
    late <Type> name, other;     // no initializer

It does NOT flag:

    late <Type> name = expr();   // has initializer (lazy init pattern)
    late final <Type> name = computeOnce();
    final <Type> name = ...;     // not late
    <Type>? name;                // explicit nullable, not late

LLMs reach for `late` because:

- It "fixes" the compile error "non-nullable field must be initialized"
  faster than restructuring the constructor or making the field
  nullable.
- The model has seen `late` in Flutter `initState` patterns and
  overgeneralizes it to fields that should be plain `final` or
  nullable.
- The runtime cost (a hidden init check on every read) and the runtime
  failure mode (`LateInitializationError`) are invisible in the
  snippet, so the model treats it as a free fix.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


def strip_comments_and_strings(text: str) -> str:
    """Blank // and /* */ comments and Dart string literals while
    preserving line numbers and length."""
    out = []
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        nxt = text[i + 1] if i + 1 < n else ""
        # /* ... */
        if ch == "/" and nxt == "*":
            j = text.find("*/", i + 2)
            if j == -1:
                for c in text[i:]:
                    out.append("\n" if c == "\n" else " ")
                return "".join(out)
            for c in text[i : j + 2]:
                out.append("\n" if c == "\n" else " ")
            i = j + 2
            continue
        # // ...
        if ch == "/" and nxt == "/":
            j = text.find("\n", i)
            if j == -1:
                out.append(" " * (n - i))
                return "".join(out)
            out.append(" " * (j - i))
            i = j
            continue
        # Raw triple string r"""..."""  / r'''...'''
        # Triple string """...""" / '''...'''
        for q in ('"""', "'''"):
            if text.startswith(q, i):
                out.append(q)
                i += 3
                while i < n:
                    if text.startswith(q, i):
                        out.append(q)
                        i += 3
                        break
                    c = text[i]
                    out.append("\n" if c == "\n" else " ")
                    i += 1
                break
        else:
            if ch in ('"', "'"):
                quote = ch
                out.append(quote)
                i += 1
                while i < n:
                    c = text[i]
                    if c == "\\" and i + 1 < n:
                        out.append("  ")
                        i += 2
                        continue
                    if c == quote:
                        out.append(quote)
                        i += 1
                        break
                    out.append("\n" if c == "\n" else " ")
                    i += 1
                continue
            out.append(ch)
            i += 1
            continue
        # we hit the triple-string break
    return "".join(out)


# Match a `late` field declaration up to the terminator (`;` or `=`).
# Capture group 1 is what comes immediately after the declarator name(s):
# either `;` (no initializer) or `=` / `(` (has initializer / is a method).
RE_LATE_DECL = re.compile(
    r"\blate\b"  # the `late` keyword
    r"(?:\s+(?:final|static|covariant))*"  # optional modifiers
    r"\s+"
    r"(?:[A-Za-z_][\w<>?,\s\.]*?)"  # type (greedy-ish, includes generics / nullable)
    r"\s+"
    r"[A-Za-z_]\w*"  # first variable name
    r"(?:\s*,\s*[A-Za-z_]\w*)*"  # optional additional names
    r"\s*([;=])"  # terminator: ; means no init, = means has init
)


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
    for m in RE_LATE_DECL.finditer(scrub):
        terminator = m.group(1)
        if terminator != ";":
            continue  # has initializer -> ok
        line, col = line_col_of(scrub, m.start())
        snippet = (
            raw_lines[line - 1].strip() if line - 1 < len(raw_lines) else ""
        )
        findings.append((path, line, col, "late-no-init", snippet))
    return findings


def iter_targets(roots: list[str]):
    for r in roots:
        p = Path(r)
        if p.is_dir():
            for sub in sorted(p.rglob("*")):
                if sub.is_file() and sub.suffix == ".dart":
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
