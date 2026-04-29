#!/usr/bin/env python3
"""Detect AppleScript dynamic-code-execution sinks.

Flags:
  - `run script <expr>` (with optional `as <type>` / `with parameters {...}`)
  - `do shell script <expr>` -- arbitrary /bin/sh execution
  - `osascript -e <expr>` invocations from inside `do shell script`
  - `load script <file>` then run -- script object loading from disk

Mask handling:
  - AppleScript line comments: `--` to EOL, plus `#` to EOL (the `#` form is
    accepted by modern osascript).
  - Block comments: `(* ... *)` (may span lines; tracked with a state flag).
  - Double-quoted strings: contents masked (AppleScript escapes are `\\"`).

Usage:
  python3 detect.py [PATH ...]
"""
from __future__ import annotations

import os
import re
import sys
from typing import Iterable, List, Tuple

EXTS = {".applescript", ".scpt.txt", ".scptd.txt", ".as"}

# Operate on masked lines. We anchor on a leading word boundary or line start.
PATTERNS: List[Tuple[str, "re.Pattern[str]"]] = [
    ("run-script",      re.compile(r"(?:^|\s)run\s+script\b")),
    ("do-shell-script", re.compile(r"(?:^|\s)do\s+shell\s+script\b")),
    ("osascript-e",     re.compile(r"\bosascript\s+-e\b")),
    ("load-script",     re.compile(r"(?:^|\s)load\s+script\b")),
]


def _mask_line(line: str, in_block: bool) -> Tuple[str, bool]:
    """Mask one line. Returns (masked_line, in_block_after)."""
    out: List[str] = []
    i, n = 0, len(line)
    in_str = False
    while i < n:
        ch = line[i]
        nxt = line[i + 1] if i + 1 < n else ""
        if in_block:
            if ch == "*" and nxt == ")":
                out.append("  ")
                i += 2
                in_block = False
                continue
            out.append(" ")
            i += 1
            continue
        if in_str:
            if ch == "\\" and i + 1 < n:
                out.append("  ")
                i += 2
                continue
            if ch == '"':
                out.append('"')
                in_str = False
                i += 1
                continue
            out.append(" ")
            i += 1
            continue
        # not in string, not in block
        if ch == "(" and nxt == "*":
            out.append("  ")
            i += 2
            in_block = True
            continue
        if ch == "-" and nxt == "-":
            # line comment to EOL
            out.append(" " * (n - i))
            break
        if ch == "#":
            out.append(" " * (n - i))
            break
        if ch == '"':
            out.append('"')
            in_str = True
            i += 1
            continue
        out.append(ch)
        i += 1
    return "".join(out), in_block


def scan_file(path: str) -> List[Tuple[int, str, str]]:
    findings: List[Tuple[int, str, str]] = []
    in_block = False
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            for lineno, raw in enumerate(fh, start=1):
                line = raw.rstrip("\n")
                masked, in_block = _mask_line(line, in_block)
                for name, pat in PATTERNS:
                    if pat.search(masked):
                        findings.append((lineno, name, line))
                        break
    except OSError as exc:
        print(f"warn: cannot read {path}: {exc}", file=sys.stderr)
    return findings


def walk(paths: Iterable[str]) -> Iterable[str]:
    for p in paths:
        if os.path.isdir(p):
            for root, _, files in os.walk(p):
                for f in files:
                    ext = os.path.splitext(f)[1]
                    if ext in EXTS or f.endswith(".applescript"):
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
