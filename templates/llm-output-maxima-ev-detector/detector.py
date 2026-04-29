#!/usr/bin/env python3
"""Detect Maxima dynamic-evaluation sinks in `.mac` / `.mc` / `.maxima` files.

Maxima is a computer-algebra system with a small but real eval-of-string
surface that LLMs reach for when asked to "let the user define their own
function" or "load this generated formula". The classic sinks are:

  ev(EXPR, ...)        - re-evaluate EXPR with extra bindings/flags. When the
                         first argument is a *string* or a runtime-built form
                         (not a literal expression the author typed), the
                         author has built an eval-of-string.
  eval_string("...")   - parse a Maxima string into a form, evaluate it.
  parse_string("...")  - parse only; pairs with ev() / eval_string() to RCE.
  batch(EXPR)          - read a file and execute its contents as Maxima.
  batchload(EXPR)      - same as batch but quieter; same RCE if path dynamic.
  load(EXPR)           - load a package; if EXPR is dynamic, RCE.

This detector is single-pass, python3 stdlib only. It masks Maxima block
comments (`/* ... */`, possibly nested via greedy line-by-line treatment)
and the interiors of `"..."` strings before regex matching.

Sinks flagged (one per line, first match wins):
  ev-call            `ev(...)`
  eval-string-call   `eval_string(...)`
  parse-string-call  `parse_string(...)`
  batch-dynamic      `batch(EXPR)` where EXPR is not a single string literal
  batchload-dynamic  `batchload(EXPR)` where EXPR is not a single string literal
  load-dynamic       `load(EXPR)` where EXPR is not a single string literal
                     and not a single bareword (Maxima's `load(diff)` etc.)

False-positives suppressed: any sink mention inside a `/* ... */` comment
or inside a `"..."` string body. Static `batch("plot.mac")` /
`batchload("init.mac")` / `load("draw")` / `load(draw)` are NOT flagged.
"""
from __future__ import annotations

import os
import re
import sys
from typing import Iterable, List, Tuple

EXTS = {".mac", ".mc", ".maxima", ".max"}

# Sinks where any call form is suspicious.
SIMPLE_CALLS: List[Tuple[str, "re.Pattern[str]"]] = [
    ("ev-call",           re.compile(r"\bev\s*\(")),
    ("eval-string-call",  re.compile(r"\beval_string\s*\(")),
    ("parse-string-call", re.compile(r"\bparse_string\s*\(")),
]

# Sinks where only a *dynamic* argument is suspicious.
# `allow_bareword=True` means a bare identifier argument is treated as static
# (idiomatic Maxima package loading: `load(draw)`). For `batch`/`batchload`
# the argument is always a *path*, so a bareword is a runtime variable -
# not static.
DYNAMIC_ARG_CALLS: List[Tuple[str, "re.Pattern[str]", bool]] = [
    ("batch-dynamic",     re.compile(r"\bbatch\s*\("),     False),
    ("batchload-dynamic", re.compile(r"\bbatchload\s*\("), False),
    ("load-dynamic",      re.compile(r"\bload\s*\("),      True),
]


def mask(src: str) -> str:
    """Blank `/* ... */` block comments and `"..."` string bodies. Preserve
    newlines so reported line numbers stay accurate."""
    out: List[str] = []
    i, n = 0, len(src)
    in_block = False
    in_str = False
    while i < n:
        c = src[i]
        if in_block:
            if c == "*" and i + 1 < n and src[i + 1] == "/":
                out.append("  ")
                i += 2
                in_block = False
                continue
            out.append("\n" if c == "\n" else " ")
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
            out.append("\n" if c == "\n" else " ")
            i += 1
            continue
        if c == "/" and i + 1 < n and src[i + 1] == "*":
            in_block = True
            out.append("  ")
            i += 2
            continue
        if c == '"':
            in_str = True
            out.append('"')
            i += 1
            continue
        out.append(c)
        i += 1
    return "".join(out)


def _extract_first_arg(masked_line: str, call_end: int) -> str:
    """Return the substring between the `(` at `call_end - 1` and its matching
    `)`, or up to the first top-level `,`. `call_end` is the index just past
    the opening `(`."""
    depth = 1
    i = call_end
    n = len(masked_line)
    start = i
    while i < n:
        c = masked_line[i]
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return masked_line[start:i]
        elif c == "," and depth == 1:
            return masked_line[start:i]
        i += 1
    return masked_line[start:n]


def _is_static_arg(arg: str, allow_bareword: bool) -> bool:
    """True if `arg` is a single string literal, or (when `allow_bareword`)
    a single bareword identifier."""
    s = arg.strip()
    if not s:
        return False
    if s.startswith('"') and s.endswith('"') and len(s) >= 2 and s.count('"') == 2:
        return True
    if allow_bareword and re.fullmatch(r"[A-Za-z_]\w*", s):
        return True
    return False


def scan_file(path: str) -> List[Tuple[int, int, str, str]]:
    findings: List[Tuple[int, int, str, str]] = []
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            src = fh.read()
    except OSError as exc:
        print(f"warn: cannot read {path}: {exc}", file=sys.stderr)
        return findings
    masked = mask(src)
    masked_lines = masked.splitlines()
    raw_lines = src.splitlines()
    for idx, m in enumerate(masked_lines):
        hit = None
        for name, pat in SIMPLE_CALLS:
            mo = pat.search(m)
            if mo:
                hit = (idx + 1, mo.start() + 1, name)
                break
        if hit is None:
            for name, pat, allow_bw in DYNAMIC_ARG_CALLS:
                mo = pat.search(m)
                if mo:
                    arg = _extract_first_arg(m, mo.end())
                    if not _is_static_arg(arg, allow_bw):
                        hit = (idx + 1, mo.start() + 1, name)
                        break
        if hit is not None:
            lineno, col, name = hit
            snippet = raw_lines[idx].strip() if idx < len(raw_lines) else ""
            findings.append((lineno, col, name, snippet))
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
