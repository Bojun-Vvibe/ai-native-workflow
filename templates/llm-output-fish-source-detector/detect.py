#!/usr/bin/env python3
"""Detect dangerous fish-shell `source` invocations on dynamic paths.

Fish's `source FILE` (and its short alias `.`) reads FILE and runs
its contents as fish code in the current shell. When FILE is built
from `$var`, a command substitution `(cmd ...)`, or process
substitution `(cmd | psub)`, an attacker who controls that value
gains arbitrary fish-script execution.

What this flags
---------------
* `source $var`
* `source (cmd ...)` / `source (curl $url | psub)`
* `source "..."` containing `$var` or `(cmd ...)` (fish double
  quotes interpolate `$var`)
* `. $var` / `. (cmd)` (fish supports `.` as alias for source)

A purely literal `source ~/.config/fish/aliases.fish` is NOT
flagged. Suppress an audited line with `# source-ok`.

Usage
-----
    python3 detect.py <file_or_dir> [...]

Exit code 1 if any findings, 0 otherwise. python3 stdlib only.
Recurses into directories looking for *.fish files and files whose
first line is a fish shebang.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


# `source` (or `.`) at command position. Fish command position: start
# of line (after optional whitespace), after `;`, after `|`, after
# `&&` / `||`, after `(` (subexpression), or after `begin`/`then`/
# `else` keywords.
RE_SOURCE = re.compile(
    r"(?:^|(?<=[;|&(])|(?<=\bbegin\s)|(?<=\bthen\s)|(?<=\belse\s))"
    r"\s*(?:source\b|\.(?=\s))([^\n]*)"
)

# Suppression marker.
RE_SUPPRESS = re.compile(r"#\s*source-ok\b")

# Anything that makes the argument dynamic. After string scrubbing,
# bare `$` indicates a variable expansion; `(` indicates command
# substitution.
RE_DYNAMIC = re.compile(r"[$(]")


def strip_comments_and_strings(line: str) -> str:
    """Blank `#`-comment tails and the *contents* of single-quoted
    fish strings, while keeping `$` / `(` characters that appear
    inside double-quoted strings (fish double quotes interpolate
    variables and command substitutions, so the danger survives a
    pass through quoting).

    Column positions are preserved.
    """
    out: list[str] = []
    i = 0
    n = len(line)
    in_sq = False
    in_dq = False
    while i < n:
        ch = line[i]
        if not in_sq and not in_dq:
            if ch == "#" and (i == 0 or line[i - 1].isspace() or line[i - 1] in ";|&("):
                out.append(" " * (n - i))
                break
            if ch == "'":
                in_sq = True
                out.append(ch)
                i += 1
                continue
            if ch == '"':
                in_dq = True
                out.append(ch)
                i += 1
                continue
            out.append(ch)
            i += 1
            continue
        if in_sq:
            # Fish single quotes: only `\'` and `\\` are escapes.
            if ch == "\\" and i + 1 < n and line[i + 1] in ("'", "\\"):
                out.append("  ")
                i += 2
                continue
            if ch == "'":
                in_sq = False
                out.append(ch)
                i += 1
                continue
            out.append(" ")
            i += 1
            continue
        # in_dq: keep `$` and `(` so a dangerous interpolation is
        # still visible. Blank everything else (including the literal
        # word "source" buried inside a docstring).
        if ch == "\\" and i + 1 < n:
            out.append("  ")
            i += 2
            continue
        if ch == '"':
            in_dq = False
            out.append(ch)
            i += 1
            continue
        if ch in "$(":
            out.append(ch)
            i += 1
            continue
        out.append(" ")
        i += 1
    return "".join(out)


def is_fish_file(path: Path) -> bool:
    if path.suffix == ".fish":
        return True
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            first = fh.readline()
    except OSError:
        return False
    if not first.startswith("#!"):
        return False
    return "fish" in first


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
        for m in RE_SOURCE.finditer(scrub):
            rest = m.group(1)
            if not RE_DYNAMIC.search(rest):
                continue
            # Column: locate the source/. token in the scrubbed line.
            tok_pos = m.start()
            # Skip leading whitespace inside the match.
            while tok_pos < len(scrub) and scrub[tok_pos].isspace():
                tok_pos += 1
            col = tok_pos + 1
            findings.append((path, idx, col, "fish-source-dynamic", raw.strip()))
    return findings


def iter_targets(roots: list[str]):
    for r in roots:
        p = Path(r)
        if p.is_dir():
            for sub in sorted(p.rglob("*")):
                if sub.is_file() and is_fish_file(sub):
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
