#!/usr/bin/env python3
"""Detect REXX dynamic-string-eval sinks.

REXX has `INTERPRET expr`, which compiles and runs the value of `expr`
as REXX source in the current variable scope — Python's `exec()` for
the REXX VM. The `VALUE()` BIF and the `(name)` indirect form on
`CALL`, `SIGNAL`, and `ADDRESS` are the same hazard with extra steps:
the *name* of the routine, label, or host environment is computed at
runtime from a string.

Out of scope (deliberately):

* `RXFUNCADD` and friends — dynamic binding, not dynamic eval.
* `INTERPRET` of a literal string — still flagged, because LLMs love
  to "demonstrate" with a literal that the next refactor turns into a
  variable.

Comments (`/* ... */`, `-- ...`) and string literals (`'...'`,
`"..."`) are masked before scanning. REXX is case-insensitive.

Suppression: trailing `/* interpret-ok */` or `-- interpret-ok` on
the same line.

Usage:
    python3 detect.py <file_or_dir> [<file_or_dir> ...]

Exit 1 if findings, 0 otherwise. python3 stdlib only. Recurses
*.rexx, *.rex, *.cmd.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


# `INTERPRET` as a statement keyword. Must be at start-of-statement,
# i.e. preceded by `;`, `:`, start-of-line, or whitespace-only prefix.
RE_INTERPRET = re.compile(
    r"(?:(?<=^)|(?<=[;:\s]))interpret\b\s+\S",
    re.IGNORECASE,
)
RE_CALL_VALUE = re.compile(
    r"(?:(?<=^)|(?<=[;:\s]))call\s+(?:value\s*\(|\(\s*[A-Za-z_])",
    re.IGNORECASE,
)
RE_SIGNAL_VALUE = re.compile(
    r"(?:(?<=^)|(?<=[;:\s]))signal\s+(?:value\s*\(|\(\s*[A-Za-z_])",
    re.IGNORECASE,
)
RE_ADDRESS_VALUE = re.compile(
    r"(?:(?<=^)|(?<=[;:\s]))address\s+(?:value\s*\(|\(\s*[A-Za-z_])",
    re.IGNORECASE,
)

RE_SUPPRESS = re.compile(
    r"(?:/\*\s*interpret-ok\s*\*/|--\s*interpret-ok\b)",
    re.IGNORECASE,
)


def strip_comments_and_strings(text: str) -> str:
    """Mask `/* ... */` block comments (may span lines), `-- ...` line
    comments, and `'...'` / `"..."` string literals.

    Block comments in REXX nest in some dialects; we treat them as
    non-nesting (the common case) and accept that nested block
    comments may be slightly under-masked — false positives there
    are noisy but safe.
    """
    out: list[str] = []
    i = 0
    n = len(text)
    in_block = False
    in_sq = False
    in_dq = False
    while i < n:
        ch = text[i]
        nxt = text[i + 1] if i + 1 < n else ""
        if in_block:
            if ch == "*" and nxt == "/":
                out.append("  ")
                i += 2
                in_block = False
                continue
            out.append(" " if ch != "\n" else "\n")
            i += 1
            continue
        if in_sq:
            if ch == "'":
                in_sq = False
                out.append("'")
                i += 1
                continue
            out.append(" " if ch != "\n" else "\n")
            i += 1
            continue
        if in_dq:
            if ch == '"':
                in_dq = False
                out.append('"')
                i += 1
                continue
            out.append(" " if ch != "\n" else "\n")
            i += 1
            continue
        # Not in any masked region.
        if ch == "/" and nxt == "*":
            out.append("  ")
            i += 2
            in_block = True
            continue
        if ch == "-" and nxt == "-":
            # Line comment: blank to end of line, keep newline.
            j = text.find("\n", i)
            if j == -1:
                out.append(" " * (n - i))
                i = n
            else:
                out.append(" " * (j - i))
                i = j
            continue
        if ch == "'":
            in_sq = True
            out.append("'")
            i += 1
            continue
        if ch == '"':
            in_dq = True
            out.append('"')
            i += 1
            continue
        out.append(ch)
        i += 1
    return "".join(out)


KINDS = (
    ("interpret", RE_INTERPRET),
    ("call-value", RE_CALL_VALUE),
    ("signal-value", RE_SIGNAL_VALUE),
    ("address-value", RE_ADDRESS_VALUE),
)


def scan_text(text: str) -> list[tuple[int, int, str, str]]:
    raw_lines = text.splitlines()
    suppressed = {
        i + 1
        for i, line in enumerate(raw_lines)
        if RE_SUPPRESS.search(line)
    }
    scrubbed = strip_comments_and_strings(text)
    scrubbed_lines = scrubbed.splitlines()
    # Pad scrubbed_lines if mismatch.
    while len(scrubbed_lines) < len(raw_lines):
        scrubbed_lines.append("")

    findings: list[tuple[int, int, str, str]] = []
    for ln, sl in enumerate(scrubbed_lines, 1):
        if ln in suppressed:
            continue
        for kind, regex in KINDS:
            for m in regex.finditer(sl):
                snippet = (
                    raw_lines[ln - 1].strip() if 1 <= ln <= len(raw_lines) else ""
                )
                findings.append((ln, m.start() + 1, kind, snippet))
                break  # one finding per line per kind is enough
    findings.sort()
    return findings


def scan_file(path: Path) -> list[tuple[Path, int, int, str, str]]:
    out: list[tuple[Path, int, int, str, str]] = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return out
    for ln, col, kind, snippet in scan_text(text):
        out.append((path, ln, col, kind, snippet))
    return out


def iter_targets(roots: list[str]):
    suffixes = {".rexx", ".rex", ".cmd"}
    for r in roots:
        p = Path(r)
        if p.is_dir():
            for sub in sorted(p.rglob("*")):
                if sub.is_file() and sub.suffix.lower() in suffixes:
                    yield sub
        elif p.is_file():
            yield p


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(f"usage: {argv[0]} <file_or_dir> [...]", file=sys.stderr)
        return 2
    total = 0
    for path in iter_targets(argv[1:]):
        for f_path, ln, col, kind, snippet in scan_file(path):
            print(f"{f_path}:{ln}:{col}: {kind} \u2014 {snippet}")
            total += 1
    print(f"# {total} finding(s)")
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
