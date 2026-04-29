#!/usr/bin/env python3
"""Detect Rebol/Red dynamic-evaluation calls.

Rebol and Red expose primitives that take a string or block at runtime
and execute it as code:

* `do STRING`        — load + evaluate a string as Rebol/Red code.
                       Equivalent to `exec()` on a string.
* `do %file.r`       — execute a script file (path may be user-controlled).
* `load STRING`      — parse a string into a block of values that's
                       almost always passed straight to `do`.
* `to-block STRING`  — convert a string to a block; same hazard when
                       paired with `do`.

LLM-emitted Rebol/Red snippets reach for `do STRING` whenever the model
needs a "config language", a "rule engine", or a "tiny REPL", because
the language's homoiconic feel makes it look safe. It is not safe when
any portion of the string is influenced by user input — the entire
language, including `delete`, `write`, and `call`, is reachable.

Usage:
    python3 detect.py <file_or_dir> [<file_or_dir> ...]

Exit 1 if any findings, 0 otherwise. python3 stdlib only.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


def strip_comments_and_strings(line: str) -> str:
    """Mask `;` line comments and "..." string literals, preserving
    column positions. Rebol strings can also use `{...}` braces, which
    nest; we mask those too. Multi-line braced strings are handled by
    the caller via `in_brace_depth`."""
    out: list[str] = []
    i = 0
    n = len(line)
    in_dq = False
    while i < n:
        ch = line[i]
        if not in_dq:
            if ch == ";":
                out.append(" " * (n - i))
                break
            if ch == '"':
                in_dq = True
                out.append(ch)
                i += 1
                continue
            out.append(ch)
            i += 1
            continue
        # inside "..." string
        if ch == "^" and i + 1 < n:
            # Rebol caret-escape: ^/, ^", ^^ etc.
            out.append("  ")
            i += 2
            continue
        if ch == '"':
            in_dq = False
            out.append(ch)
            i += 1
            continue
        out.append(" ")
        i += 1
    return "".join(out)


def mask_brace_strings(line: str, depth: int) -> tuple[str, int]:
    """Mask `{...}` Rebol multi-line string literals (which nest)
    while preserving column positions. Returns (masked_line, new_depth).
    Caret escape `^{` and `^}` are honored."""
    out: list[str] = []
    i = 0
    n = len(line)
    while i < n:
        ch = line[i]
        if depth > 0:
            if ch == "^" and i + 1 < n:
                out.append("  ")
                i += 2
                continue
            if ch == "{":
                depth += 1
                out.append(" ")
                i += 1
                continue
            if ch == "}":
                depth -= 1
                out.append(" ")
                i += 1
                continue
            out.append(" ")
            i += 1
            continue
        if ch == "{":
            depth = 1
            out.append("{")
            i += 1
            continue
        out.append(ch)
        i += 1
    return "".join(out), depth


# Word boundary in Rebol: words are separated by whitespace, brackets,
# parens, or string delimiters. Use a custom prev-char check to ensure
# `do` is a standalone word (not e.g. `redo` or `do-stuff`).
RE_PATTERNS = [
    ("rebol-do-string", re.compile(r"(?<![A-Za-z0-9!?\-_*+/<>=&|.~])do\s+\"")),
    ("rebol-do-brace", re.compile(r"(?<![A-Za-z0-9!?\-_*+/<>=&|.~])do\s+\{")),
    ("rebol-do-file", re.compile(r"(?<![A-Za-z0-9!?\-_*+/<>=&|.~])do\s+%")),
    ("rebol-do-load", re.compile(r"(?<![A-Za-z0-9!?\-_*+/<>=&|.~])do\s+load\b")),
    ("rebol-do-to-block", re.compile(r"(?<![A-Za-z0-9!?\-_*+/<>=&|.~])do\s+to-block\b")),
    ("rebol-load-then-do", re.compile(r"(?<![A-Za-z0-9!?\-_*+/<>=&|.~])load\s+\"")),
]


def scan_file(path: Path) -> list[tuple[Path, int, int, str, str]]:
    findings: list[tuple[Path, int, int, str, str]] = []
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return findings
    brace_depth = 0
    for idx, raw_line in enumerate(raw.splitlines()):
        lineno = idx + 1
        masked_braces, brace_depth = mask_brace_strings(raw_line, brace_depth)
        scrub = strip_comments_and_strings(masked_braces)
        for kind, pat in RE_PATTERNS:
            for m in pat.finditer(scrub):
                findings.append(
                    (path, lineno, m.start() + 1, kind, raw_line.strip())
                )
    return findings


def iter_targets(roots: list[str]):
    for r in roots:
        p = Path(r)
        if p.is_dir():
            for sub in sorted(
                list(p.rglob("*.r"))
                + list(p.rglob("*.r3"))
                + list(p.rglob("*.reb"))
                + list(p.rglob("*.red"))
            ):
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
