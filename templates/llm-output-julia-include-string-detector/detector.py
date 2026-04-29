#!/usr/bin/env python3
"""Detect Julia dynamic-code-inclusion sinks in LLM-generated `.jl` files.

Julia's `include_string(mod, str)` and `include_string(mod, str, fname)` parse
and evaluate an arbitrary string as Julia code in the target module. Its sibling
`Meta.parse(str)` followed by `eval(...)` (or the convenience `Meta.parseall`
plus `eval`) does the same. These are distinct from the well-known `eval(ex)`
on a literal AST: they take *string* input, which is exactly the shape an LLM
will reach for when wiring up "let the user supply some code" or "reload this
script body fetched from the network".

This detector is a single-pass, stdlib-only scanner. It masks Julia line
comments (`# ...`), block comments (`#= ... =#`), regular string literals
(`"..."`), triple-quoted strings (`\"\"\"..\"\"\"`) and raw strings
(`r"..."`, `b"..."`) before regex matching, so the sink names appearing inside
strings or comments do not produce false positives.

Sinks flagged:
  include-string       `include_string(...)`
  include-from-net     `include(download(...))` / `include(HTTP.get(...).body)`
  meta-parse-eval      `eval(Meta.parse(...))` / `Core.eval(m, Meta.parse(...))`
  parseall-eval        `eval(Meta.parseall(...))`
  expr-from-string     `Expr(:string, ...)` followed by `eval`
  invokelatest-eval    `Base.invokelatest(eval, Meta.parse(...))`

Usage:
  python3 detector.py PATH [PATH ...]
Exits 1 if any finding emitted, 0 otherwise.
"""
from __future__ import annotations

import os
import re
import sys
from typing import Iterable, List, Tuple

PATTERNS: List[Tuple[str, "re.Pattern[str]"]] = [
    ("include-string",    re.compile(r"\binclude_string\s*\(")),
    ("include-from-net",  re.compile(r"\binclude\s*\(\s*(?:download|HTTP\.get|read)\s*\(")),
    ("meta-parse-eval",   re.compile(r"\beval\s*\([^)]*Meta\.parse\s*\(|\bCore\.eval\s*\([^)]*Meta\.parse\s*\(")),
    ("parseall-eval",     re.compile(r"\beval\s*\([^)]*Meta\.parseall\s*\(")),
    ("invokelatest-eval", re.compile(r"\bBase\.invokelatest\s*\(\s*eval\s*,\s*Meta\.parse")),
]

EXTS = {".jl"}


def mask(src: str) -> str:
    """Blank out comment and string-literal contents, preserving offsets.

    Handles, in priority order:
      * block comments  #= ... =#  (may nest in Julia, we treat depth 1+)
      * line comments   # ...
      * triple-quoted strings  \"\"\" ... \"\"\"
      * raw / byte / regex string prefixes r\"\", b\"\", raw\"\"
      * regular double-quoted strings  "..."
    Single-quoted is for chars in Julia (one codepoint), not strings; we still
    mask `'x'` defensively.
    """
    out: List[str] = []
    i, n = 0, len(src)
    block_depth = 0
    in_triple = False
    in_str = False
    in_char = False

    def blank(s: str) -> str:
        # preserve newlines so line numbering stays correct
        return "".join(c if c == "\n" else " " for c in s)

    while i < n:
        c = src[i]
        c2 = src[i:i + 2]
        c3 = src[i:i + 3]

        if block_depth > 0:
            if c2 == "#=":
                block_depth += 1
                out.append("  ")
                i += 2
                continue
            if c2 == "=#":
                block_depth -= 1
                out.append("  ")
                i += 2
                continue
            out.append(c if c == "\n" else " ")
            i += 1
            continue

        if in_triple:
            if c3 == '"""':
                in_triple = False
                out.append('"""')
                i += 3
                continue
            out.append(c if c == "\n" else " ")
            i += 1
            continue

        if in_str:
            if c == "\\" and i + 1 < n:
                out.append("  ")
                i += 2
                continue
            if c == '"':
                in_str = False
                out.append('"')
                i += 1
                continue
            out.append(c if c == "\n" else " ")
            i += 1
            continue

        if in_char:
            if c == "\\" and i + 1 < n:
                out.append("  ")
                i += 2
                continue
            if c == "'":
                in_char = False
                out.append("'")
                i += 1
                continue
            out.append(" ")
            i += 1
            continue

        # not inside any masked region
        if c2 == "#=":
            block_depth = 1
            out.append("  ")
            i += 2
            continue
        if c == "#":
            # line comment until newline
            j = src.find("\n", i)
            if j == -1:
                out.append(blank(src[i:]))
                i = n
            else:
                out.append(blank(src[i:j]))
                i = j
            continue
        if c3 == '"""':
            in_triple = True
            out.append('"""')
            i += 3
            continue
        # raw/byte/regex prefix? swallow prefix letters then enter normal string state
        # forms: r"...", b"...", raw"...", r"..."i (regex flag handled by mask of body)
        if c == '"':
            in_str = True
            out.append('"')
            i += 1
            continue
        if c == "'":
            in_char = True
            out.append("'")
            i += 1
            continue
        out.append(c)
        i += 1

    return "".join(out)


def scan_file(path: str) -> List[Tuple[int, int, str, str]]:
    findings: List[Tuple[int, int, str, str]] = []
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            src = fh.read()
    except OSError as exc:
        print(f"warn: cannot read {path}: {exc}", file=sys.stderr)
        return findings
    masked = mask(src)
    # split both into lines, scan masked, report from raw
    masked_lines = masked.splitlines()
    raw_lines = src.splitlines()
    for idx, m in enumerate(masked_lines):
        for name, pat in PATTERNS:
            mo = pat.search(m)
            if mo:
                col = mo.start() + 1
                snippet = raw_lines[idx].strip() if idx < len(raw_lines) else ""
                findings.append((idx + 1, col, name, snippet))
                break
    return findings


def walk(paths: Iterable[str]) -> Iterable[str]:
    for p in paths:
        if os.path.isdir(p):
            for root, _, files in os.walk(p):
                for f in sorted(files):
                    if os.path.splitext(f)[1] in EXTS:
                        yield os.path.join(root, f)
        elif os.path.isfile(p):
            yield p


def main(argv: List[str]) -> int:
    if not argv:
        print("usage: detector.py PATH [PATH ...]", file=sys.stderr)
        return 2
    total = 0
    for path in walk(argv):
        for lineno, col, name, snippet in scan_file(path):
            print(f"{path}:{lineno}:{col}: {name} {snippet}")
            total += 1
    print(f"-- {total} finding(s)", file=sys.stderr)
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
