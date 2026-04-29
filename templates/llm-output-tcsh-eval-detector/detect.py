#!/usr/bin/env python3
"""Detect dangerous tcsh/csh `eval` invocations on dynamic data.

tcsh's `eval string ...` re-parses its arguments through the full
shell parser — globbing, history substitution, command substitution,
variable expansion, and execution. When any of those arguments are
built from a `$var`, a backtick command substitution `` `cmd` ``, or
a history reference like `!$`, an attacker who controls that value
gains arbitrary tcsh execution.

What this flags
---------------
* `eval $var`
* `eval "$var"`            (csh double quotes interpolate `$var`)
* `eval `cmd``             (backtick command substitution)
* `eval "prefix $x suffix"`
* `eval !$` / `eval !*`    (history expansion of recent words)
* `eval` after `;`, `|`, `&&`, `||`, `(`, `then`, `else`

What this does NOT flag
-----------------------
* `eval 'literal single-quoted string'` (csh single quotes are
  inert; no interpolation, no history)
* `eval echo hello`         (no `$`, no backtick, no `!`)
* Lines marked with a trailing `# eval-ok` suppression comment

Usage
-----
    python3 detect.py <file_or_dir> [...]

Exit code 1 if any findings, 0 otherwise. python3 stdlib only.
Recurses directories looking for *.tcsh, *.csh, and files whose
first line is a `#!.../tcsh` or `#!.../csh` shebang.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


# `eval` at csh command position: start of line (after optional
# whitespace), after `;`, `|`, `&&`, `||`, `(`, or after the keywords
# `then` / `else`.
RE_EVAL = re.compile(
    r"(?:^|(?<=[;|&(])|(?<=\bthen\s)|(?<=\belse\s))"
    r"\s*eval\b([^\n]*)"
)

# Suppression marker.
RE_SUPPRESS = re.compile(r"#\s*eval-ok\b")

# Anything that makes the argument dynamic after string scrubbing:
#   $   variable expansion
#   `   backtick command substitution
#   !   history expansion (csh-specific)
RE_DYNAMIC = re.compile(r"[$`!]")


def strip_comments_and_strings(line: str) -> str:
    """Blank `#`-comment tails and the *contents* of single-quoted
    csh strings, while keeping `$`, `` ` ``, and `!` characters that
    appear inside double-quoted strings (csh double quotes still
    interpolate variables, command substitutions, and history).

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
            # csh comments: `#` only at start of word.
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
            # csh single quotes: no escapes recognized inside.
            if ch == "'":
                in_sq = False
                out.append(ch)
                i += 1
                continue
            out.append(" ")
            i += 1
            continue
        # in_dq: keep $ ` ! so dangerous interpolation is still
        # visible. Blank everything else (including a literal "eval"
        # buried inside a docstring).
        if ch == "\\" and i + 1 < n:
            # csh `\` inside dq escapes `$`, `` ` ``, `"`, `\`, and
            # newline. Blank both chars to be safe.
            out.append("  ")
            i += 2
            continue
        if ch == '"':
            in_dq = False
            out.append(ch)
            i += 1
            continue
        if ch in "$`!":
            out.append(ch)
            i += 1
            continue
        out.append(" ")
        i += 1
    return "".join(out)


def is_csh_file(path: Path) -> bool:
    if path.suffix in (".tcsh", ".csh"):
        return True
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            first = fh.readline()
    except OSError:
        return False
    if not first.startswith("#!"):
        return False
    return "tcsh" in first or "csh" in first


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
            findings.append((path, idx, col, "tcsh-eval-dynamic", raw.strip()))
    return findings


def iter_targets(roots: list[str]):
    for r in roots:
        p = Path(r)
        if p.is_dir():
            for sub in sorted(p.rglob("*")):
                if sub.is_file() and is_csh_file(sub):
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
