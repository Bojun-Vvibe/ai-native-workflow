#!/usr/bin/env python3
"""Detect dangerous yash `eval` invocations on dynamic data.

yash is a POSIX-compliant shell. Like every POSIX shell, its `eval`
builtin concatenates its arguments with spaces and re-parses the
result as shell input — full word splitting, parameter expansion,
command substitution, redirection, the lot. When any argument is
built from a `$var` / `${var}`, a `$(cmd)` command substitution, or
a backtick `` `cmd` `` substitution, an attacker who controls that
value gains arbitrary yash execution.

What this flags
---------------
* `eval $var` / `eval ${var}` / `eval "${var:-x}"`
* `eval "$(cmd)"`             (POSIX command substitution)
* `eval `cmd``                (legacy backtick form)
* `eval "prefix $x suffix"`   (yash double quotes interpolate `$`)
* `eval` at command position (start of line, after `;`, `|`, `&&`,
  `||`, `(`, or after `then` / `else` / `do`)

What this does NOT flag
-----------------------
* `eval 'literal single-quoted string'` (POSIX single quotes are
  inert — no expansion of any kind)
* `eval echo hello`          (no `$`, no `$(`, no backtick)
* Lines marked with a trailing `# eval-ok` suppression comment

Usage
-----
    python3 detect.py <file_or_dir> [...]

Exit code 1 if any findings, 0 otherwise. python3 stdlib only.
Recurses directories looking for *.yash files and any file whose
first line is a `#!.../yash` shebang.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


# `eval` at POSIX-shell command position: start of line (after
# optional whitespace), after `;`, `|`, `&`, `(`, or after the
# keywords `then` / `else` / `do`.
RE_EVAL = re.compile(
    r"(?:^|(?<=[;|&(])|(?<=\bthen\s)|(?<=\belse\s)|(?<=\bdo\s))"
    r"\s*eval\b([^\n]*)"
)

# Suppression marker.
RE_SUPPRESS = re.compile(r"#\s*eval-ok\b")

# Anything that makes the argument dynamic after string scrubbing:
#   $   parameter expansion or $(...) command substitution
#   `   backtick command substitution
RE_DYNAMIC = re.compile(r"[$`]")


def strip_comments_and_strings(line: str) -> str:
    """Blank `#`-comment tails and the *contents* of single-quoted
    POSIX strings, while keeping `$` and `` ` `` characters that
    appear inside double-quoted strings (POSIX double quotes still
    interpolate parameter expansions and command substitutions).

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
            # POSIX comments: `#` only at start of word.
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
            # POSIX single quotes: no escapes — only the next `'`
            # ends the string.
            if ch == "'":
                in_sq = False
                out.append(ch)
                i += 1
                continue
            out.append(" ")
            i += 1
            continue
        # in_dq: keep `$` and `` ` `` so dangerous interpolation is
        # still visible. Blank everything else (including the
        # literal word "eval" buried inside a docstring).
        if ch == "\\" and i + 1 < n:
            # Inside dq, `\` only escapes `$ ` " \ <newline>`. Blank
            # both chars; this avoids a false `$` survivor on
            # `\$literal`.
            out.append("  ")
            i += 2
            continue
        if ch == '"':
            in_dq = False
            out.append(ch)
            i += 1
            continue
        if ch in "$`":
            out.append(ch)
            i += 1
            continue
        out.append(" ")
        i += 1
    return "".join(out)


def is_yash_file(path: Path) -> bool:
    if path.suffix == ".yash":
        return True
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            first = fh.readline()
    except OSError:
        return False
    if not first.startswith("#!"):
        return False
    return "yash" in first


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
        for m in RE_EVAL.finditer(scrub):
            rest = m.group(1)
            if not RE_DYNAMIC.search(rest):
                continue
            tok_pos = m.start()
            while tok_pos < len(scrub) and scrub[tok_pos].isspace():
                tok_pos += 1
            col = tok_pos + 1
            findings.append((path, idx, col, "yash-eval-dynamic", raw.strip()))
    return findings


def iter_targets(roots: list[str]):
    for r in roots:
        p = Path(r)
        if p.is_dir():
            for sub in sorted(p.rglob("*")):
                if sub.is_file() and is_yash_file(sub):
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
