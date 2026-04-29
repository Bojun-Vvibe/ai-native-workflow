#!/usr/bin/env python3
"""Detect MUMPS / Caché ObjectScript dynamic-string-eval sinks.

MUMPS has `XECUTE expr` (abbrev `X expr`) which compiles the string
`expr` as MUMPS source and runs it in the current scope — Python's
`exec()` equivalent. The `@` indirection operator does the same in
expression position: `S @x=1`, `D @x`, `G @x`, `$$@x()`.

Comments (`; ...` to end of line) and string literals (`"..."`, with
`""` as the escape for a literal quote) are masked before scanning.
MUMPS is case-insensitive.

Suppression: trailing `;xecute-ok` on the same line.

Usage:
    python3 detect.py <file_or_dir> [<file_or_dir> ...]

Exit 1 if findings, 0 otherwise. python3 stdlib only. Recurses
*.m, *.mac, *.int, *.cos.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


# `XECUTE` or its abbreviation `X` as a command. Commands in MUMPS
# stand at the start of a line (after an optional label and one or
# more leading spaces / dots) or after `  ` (two spaces) on the same
# line as a separator. We require a word-boundary on the left and at
# least one space + something on the right.
RE_XECUTE = re.compile(
    r"(?:(?<=^)|(?<=[\s.]))x(?:ecute)?\b\s+\S",
    re.IGNORECASE,
)
# Name-indirection operator `@` followed by an identifier or `(`.
# Excludes `@"..."` literal-text indirection cases? No — those are
# *also* dangerous when the literal was built by concatenation, but
# we only see the post-mask form so a bare `@"` is a literal-text
# indirection of a constant string and we flag it too.
RE_INDIRECT = re.compile(
    r"@(?:[A-Za-z%][A-Za-z0-9]*|\()"
)

RE_SUPPRESS = re.compile(r";\s*xecute-ok\b", re.IGNORECASE)


def strip_comments_and_strings(text: str) -> str:
    """Mask `; ...` line comments and `"..."` string literals.

    MUMPS uses doubled quotes to embed a literal quote inside a
    string, so `"a""b"` is the four-character string `a"b`. The
    masker tracks this so embedded `""` does not prematurely end
    the string.
    """
    out: list[str] = []
    i = 0
    n = len(text)
    in_str = False
    while i < n:
        ch = text[i]
        nxt = text[i + 1] if i + 1 < n else ""
        if in_str:
            if ch == '"' and nxt == '"':
                # Embedded literal quote — stay in string.
                out.append("  ")
                i += 2
                continue
            if ch == '"':
                in_str = False
                out.append('"')
                i += 1
                continue
            out.append(" " if ch != "\n" else "\n")
            i += 1
            continue
        # Not in string.
        if ch == ";":
            # Line comment — blank to newline, keep newline.
            j = text.find("\n", i)
            if j == -1:
                out.append(" " * (n - i))
                i = n
            else:
                out.append(" " * (j - i))
                i = j
            continue
        if ch == '"':
            in_str = True
            out.append('"')
            i += 1
            continue
        out.append(ch)
        i += 1
    return "".join(out)


KINDS = (
    ("xecute", RE_XECUTE),
    ("indirection", RE_INDIRECT),
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
                break  # one finding per line per kind
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
    suffixes = {".m", ".mac", ".int", ".cos"}
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
