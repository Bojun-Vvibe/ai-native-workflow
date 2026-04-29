#!/usr/bin/env python3
"""Detect GAP `EvalString(...)` runtime code-evaluation sinks.

GAP (Groups, Algorithms, Programming) is a computer-algebra
language widely used in mathematics. Its standard library exposes:

    EvalString( str )
    EvalString( str, scope )

which parses and evaluates the GAP expression in `str` at runtime
inside the live workspace. The result has full access to the
session's bindings, the OS-facing functions (`Exec`, `IO_*`,
`Filename`), and any loaded packages.

A close cousin worth flagging is the read-string idiom:

    ReadAsFunction( InputTextString( src ) )

This compiles `src` as a function body and returns it; calling the
result executes arbitrary GAP code, equivalent in power to
`EvalString` but spelled differently.

Whenever the source argument is anything other than a manifest,
audited literal, the program is loading code chosen at runtime from
data that may be attacker-controllable: a workspace file, a
network response, a notebook cell, a package fixture.

LLM-emitted GAP code reaches for `EvalString` whenever the model
wants "let the user paste a polynomial" or "load a saved object as
code" without knowing the safer patterns (a dedicated parser, the
JSON-style `EvalFromString` of a fixed grammar, or
`Read`-from-file with a pre-vetted path).

What this flags
---------------
* `EvalString( ... )`                              — primary sink
* `ReadAsFunction( InputTextString( ... ) )`       — read-string variant

We anchor on the symbol not preceded by an identifier character,
followed by `(`. Identifiers that merely contain `EvalString`
(`MyEvalStringHelper`, `EvalStrings`, `xEvalString`) do not match.

Suppression
-----------
Append `# eval-ok` to the line to silence a vetted call.

Usage
-----
    python3 detect.py <file_or_dir> [<file_or_dir> ...]

Exit code 1 if any findings, 0 otherwise. python3 stdlib only.
Recurses into directories looking for `*.g`, `*.gap`, `*.gi`,
`*.gd`.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


RE_SUPPRESS = re.compile(r"#\s*eval-ok\b")

RE_EVAL_STRING = re.compile(
    r"(?<![A-Za-z0-9_])EvalString\s*\("
)

# ReadAsFunction(InputTextString(...)) — allow whitespace between
# the two calls and inside the outer parens.
RE_READ_AS_FUNCTION = re.compile(
    r"(?<![A-Za-z0-9_])ReadAsFunction\s*\(\s*InputTextString\s*\("
)


def mask_gap_comments_and_strings(text: str) -> str:
    """Replace comment and string-literal interiors with spaces while
    preserving column positions and newlines.

    GAP lexical rules we cover:
      * `#` line comments (to end of line)
      * `"..."` strings with `\\` escapes
      * `'x'` character literals with `\\` escapes
    """
    out = list(text)
    n = len(text)
    i = 0
    while i < n:
        ch = text[i]
        # `#` line comment
        if ch == "#":
            j = text.find("\n", i)
            if j == -1:
                j = n
            for k in range(i, j):
                out[k] = " "
            i = j
            continue
        # "..." string
        if ch == '"':
            k = i + 1
            while k < n:
                c = text[k]
                if c == "\\" and k + 1 < n:
                    k += 2
                    continue
                if c == '"' or c == "\n":
                    break
                k += 1
            end = k + 1 if k < n and text[k] == '"' else k
            for m in range(i + 1, max(i + 1, end - 1)):
                if text[m] != "\n":
                    out[m] = " "
            i = end
            continue
        # '...' character literal
        if ch == "'":
            k = i + 1
            while k < n:
                c = text[k]
                if c == "\\" and k + 1 < n:
                    k += 2
                    continue
                if c == "'" or c == "\n":
                    break
                k += 1
            end = k + 1 if k < n and text[k] == "'" else k
            for m in range(i + 1, max(i + 1, end - 1)):
                if text[m] != "\n":
                    out[m] = " "
            i = end
            continue
        i += 1
    return "".join(out)


def scan_file(path: Path) -> list[tuple[Path, int, int, str, str]]:
    findings: list[tuple[Path, int, int, str, str]] = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return findings
    masked = mask_gap_comments_and_strings(text)
    raw_lines = text.splitlines()
    masked_lines = masked.splitlines()
    n = min(len(raw_lines), len(masked_lines))
    for idx in range(n):
        raw = raw_lines[idx]
        scrub = masked_lines[idx]
        if RE_SUPPRESS.search(raw):
            continue
        for m in RE_READ_AS_FUNCTION.finditer(scrub):
            findings.append(
                (path, idx + 1, m.start() + 1,
                 "gap-readasfunction-inputtextstring", raw.strip())
            )
        for m in RE_EVAL_STRING.finditer(scrub):
            findings.append(
                (path, idx + 1, m.start() + 1,
                 "gap-evalstring", raw.strip())
            )
    return findings


GAP_SUFFIXES = {".g", ".gap", ".gi", ".gd"}


def is_gap_file(path: Path) -> bool:
    return path.suffix in GAP_SUFFIXES


def iter_targets(roots: list[str]):
    for r in roots:
        p = Path(r)
        if p.is_dir():
            for sub in sorted(p.rglob("*")):
                if sub.is_file() and is_gap_file(sub):
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
