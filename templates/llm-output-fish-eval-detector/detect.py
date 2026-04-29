#!/usr/bin/env python3
"""Detect fish-shell `eval` / `source -` style dynamic execution sinks.

Single-pass scanner. Masks line comments (`# ...`) and string-literal contents
(both single and double quoted) before regex matching, so eval mentioned inside
a string or comment does not produce a finding.

Findings flag:
  - bare `eval ...` invocations on a fish line
  - `eval (...)` with command-substitution argument
  - `source -` / `. -` reading from stdin
  - `string ... | source` piping arbitrary text into the shell parser

Usage:
  python3 detect.py [PATH ...]
Exits 0 on no findings, 1 if any finding emitted.
"""
from __future__ import annotations

import os
import re
import sys
from typing import Iterable, List, Tuple

# Match assoc patterns on a *masked* line (comments + string contents removed).
# fish syntax is whitespace-sensitive; we anchor on word boundaries.
PATTERNS: List[Tuple[str, "re.Pattern[str]"]] = [
    ("eval-with-cmdsub", re.compile(r"(?:^|[;&|\s])eval\s+\(")),
    ("eval-with-var",    re.compile(r"(?:^|[;&|\s])eval\s+\$\w+")),
    ("eval-bare",        re.compile(r"(?:^|[;&|\s])eval\s+\S")),
    ("source-stdin",     re.compile(r"(?:^|[;&|\s])(?:source|\.)\s+-(?:\s|$)")),
    ("pipe-to-source",   re.compile(r"\|\s*(?:source|\.)\b")),
]

EXTS = {".fish"}


def mask(line: str) -> str:
    """Strip comments and string-literal contents, preserving column count."""
    out: List[str] = []
    i, n = 0, len(line)
    in_s: str | None = None  # active quote char or None
    while i < n:
        ch = line[i]
        if in_s is None:
            if ch == "#":
                # rest is comment -> blank it
                out.append(" " * (n - i))
                break
            if ch in ("'", '"'):
                in_s = ch
                out.append(ch)
                i += 1
                continue
            out.append(ch)
            i += 1
        else:
            # inside string: blank everything until matching quote.
            # fish double-quote allows \" escape; single-quote allows \' and \\.
            if ch == "\\" and i + 1 < n:
                out.append("  ")
                i += 2
                continue
            if ch == in_s:
                out.append(ch)
                in_s = None
                i += 1
                continue
            out.append(" ")
            i += 1
    return "".join(out)


def scan_file(path: str) -> List[Tuple[int, str, str]]:
    findings: List[Tuple[int, str, str]] = []
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            for lineno, raw in enumerate(fh, start=1):
                m = mask(raw.rstrip("\n"))
                for name, pat in PATTERNS:
                    if pat.search(m):
                        findings.append((lineno, name, raw.rstrip("\n")))
                        break
    except OSError as exc:
        print(f"warn: cannot read {path}: {exc}", file=sys.stderr)
    return findings


def walk(paths: Iterable[str]) -> Iterable[str]:
    for p in paths:
        if os.path.isdir(p):
            for root, _, files in os.walk(p):
                for f in files:
                    if os.path.splitext(f)[1] in EXTS:
                        yield os.path.join(root, f)
        elif os.path.isfile(p):
            yield p


def main(argv: List[str]) -> int:
    if not argv:
        print("usage: detect.py PATH [PATH ...]", file=sys.stderr)
        return 2
    total = 0
    for path in walk(argv):
        results = scan_file(path)
        if results:
            for lineno, name, src in results:
                print(f"{path}:{lineno}: [{name}] {src.strip()}")
            total += len(results)
    print(f"-- {total} finding(s)")
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
