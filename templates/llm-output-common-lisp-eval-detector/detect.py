#!/usr/bin/env python3
"""Detect Common Lisp dynamic-evaluation calls.

Common Lisp exposes several primitives that take an arbitrary form or
string at runtime and execute it in the global environment:

* `(eval FORM)`            — evaluate a Lisp form in the null lexical env.
* `(read-from-string STR)` — parse a string into a form (often paired
                              with `eval`).
* `(compile nil FORM)`     — compile then return a function; commonly
                              wrapped around user input.
* `(load FILE)`            — load and execute a Lisp file path that may
                              come from user input.

LLM-emitted Lisp reaches for these constantly when asked to build a
"REPL", a "rule engine", or a "config DSL", because the model conflates
S-expressions with safe data. Combined with `read-from-string`, this is
arbitrary code execution.

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
    column positions. Common Lisp uses `\\` to escape inside strings.
    Block comments `#| ... |#` are tracked across lines by the caller."""
    out: list[str] = []
    i = 0
    n = len(line)
    in_s = False
    while i < n:
        ch = line[i]
        if not in_s:
            if ch == ";":
                # rest of line is comment
                out.append(" " * (n - i))
                break
            if ch == '"':
                in_s = True
                out.append(ch)
                i += 1
                continue
            out.append(ch)
            i += 1
            continue
        # inside string
        if ch == "\\" and i + 1 < n:
            out.append("  ")
            i += 2
            continue
        if ch == '"':
            in_s = False
            out.append(ch)
            i += 1
            continue
        out.append(" ")
        i += 1
    return "".join(out)


# Match `(<op>` where op is one of the dangerous primitives, possibly
# package-qualified (`cl:eval`, `common-lisp:eval`).
DANGEROUS = (
    "eval",
    "read-from-string",
    "compile",
    "load",
    "eval-when",  # not strictly eval, but sometimes used to gate user code
)
# We'll detect each explicitly to give precise kind labels.
RE_PATTERNS = [
    ("cl-eval", re.compile(r"\(\s*(?:cl:|common-lisp:)?eval\b")),
    ("cl-read-from-string", re.compile(r"\(\s*(?:cl:|common-lisp:)?read-from-string\b")),
    ("cl-compile", re.compile(r"\(\s*(?:cl:|common-lisp:)?compile\s+nil\b")),
    ("cl-load", re.compile(r"\(\s*(?:cl:|common-lisp:)?load\b")),
]


def scan_file(path: Path) -> list[tuple[Path, int, int, str, str]]:
    findings: list[tuple[Path, int, int, str, str]] = []
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return findings

    in_block = 0  # nesting depth for #| ... |#
    for idx, raw_line in enumerate(raw.splitlines()):
        lineno = idx + 1
        # Process block comments character-wise so we strip them out
        # before string/comment masking on this line.
        line_chars: list[str] = []
        i = 0
        n = len(raw_line)
        while i < n:
            two = raw_line[i:i + 2]
            if in_block > 0:
                if two == "|#":
                    in_block -= 1
                    line_chars.append("  ")
                    i += 2
                    continue
                if two == "#|":
                    in_block += 1
                    line_chars.append("  ")
                    i += 2
                    continue
                line_chars.append(" ")
                i += 1
                continue
            if two == "#|":
                in_block += 1
                line_chars.append("  ")
                i += 2
                continue
            line_chars.append(raw_line[i])
            i += 1
        no_block = "".join(line_chars)
        scrub = strip_comments_and_strings(no_block)

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
                list(p.rglob("*.lisp"))
                + list(p.rglob("*.lsp"))
                + list(p.rglob("*.cl"))
                + list(p.rglob("*.asd"))
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
