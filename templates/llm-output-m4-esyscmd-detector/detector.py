#!/usr/bin/env python3
"""Detect shell-out / dynamic-eval sinks in GNU m4 input.

See README.md for rationale and rules. python3 stdlib only.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


RE_SUPPRESS = re.compile(r"\bdnl\s+m4-exec-ok\b|#\s*m4-exec-ok\b")

# Builtin name immediately followed by `(`. We stop the argument span
# at the matching `)` on the same scrubbed line; nested parens inside
# m4 quoting will already have been blanked by the scrubber.
RE_CALL = re.compile(r"\b(syscmd|esyscmd|eval|include|sinclude)\s*\(([^()]*)\)")


def strip_comments_and_strings(line: str) -> str:
    """Blank `dnl ...EOL`, `# ...EOL`, and the *contents* of m4
    quoted strings (`` `...' `` with nesting). Quote characters are
    preserved so callers can still see the empty-literal shape."""
    n = len(line)

    # `dnl ` style comment -- everything from `dnl` to EOL goes.
    m = re.search(r"\bdnl\b", line)
    dnl_cut = m.start() if m else n

    # `#` style comment (GNU m4 honors it at column-0-ish; we treat
    # any `#` outside a quoted string the same way for safety).
    out: list[str] = []
    i = 0
    depth = 0  # m4 quote nesting depth
    cut = min(n, dnl_cut)
    while i < cut:
        ch = line[i]
        if depth == 0:
            if ch == "#":
                out.append(" " * (cut - i))
                break
            if ch == "`":
                depth = 1
                out.append(ch)
                i += 1
                continue
            out.append(ch)
            i += 1
            continue
        # inside a quoted m4 string
        if ch == "`":
            depth += 1
            out.append(" ")
            i += 1
            continue
        if ch == "'":
            depth -= 1
            if depth == 0:
                out.append(ch)
            else:
                out.append(" ")
            i += 1
            continue
        out.append(" ")
        i += 1
    # pad the cut tail (for the dnl region) with spaces so column
    # offsets line up with the original line.
    out.append(" " * (n - cut))
    return "".join(out)


def is_bare_string_literal(scrubbed_arg: str) -> bool:
    """A bare m4 quoted literal scrubs to `` ` ' `` (with only spaces
    between the backtick and the apostrophe)."""
    s = scrubbed_arg.strip()
    if len(s) < 2:
        return False
    if s[0] != "`" or s[-1] != "'":
        return False
    return s[1:-1].strip() == ""


def is_m4_file(path: Path) -> bool:
    if path.suffix in (".m4", ".ac", ".am"):
        return True
    return path.name in ("configure.ac", "aclocal.m4", "configure.in")


def scan_file(path: Path) -> list[tuple[Path, int, int, str, str]]:
    findings: list[tuple[Path, int, int, str, str]] = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return findings
    for idx, raw in enumerate(text.splitlines(), start=1):
        if RE_SUPPRESS.search(raw):
            continue
        scrub = strip_comments_and_strings(raw)
        for m in RE_CALL.finditer(scrub):
            name = m.group(1)
            arg = m.group(2)
            bare = is_bare_string_literal(arg)
            if name in ("syscmd", "esyscmd"):
                kind = f"m4-{name}" if bare else f"m4-{name}-dynamic"
            elif name == "eval":
                if bare:
                    continue  # bare integer-literal eval is fine
                kind = "m4-eval-dynamic"
            else:  # include / sinclude
                if bare:
                    continue
                kind = "m4-include-dynamic"
            findings.append((path, idx, m.start() + 1, kind, raw.strip()))
    return findings


def iter_targets(roots: list[str]):
    for r in roots:
        p = Path(r)
        if p.is_dir():
            for sub in sorted(p.rglob("*")):
                if sub.is_file() and is_m4_file(sub):
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
