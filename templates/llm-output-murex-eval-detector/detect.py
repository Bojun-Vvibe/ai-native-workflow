#!/usr/bin/env python3
"""Detect dangerous Murex `eval` invocations on dynamic data.

Murex (https://murex.rocks) is a typed, content-aware POSIX-ish
shell aimed at DevOps. Its `eval` builtin takes a string of
murex source code and parses + executes it at runtime. As with
every shell-eval, the moment any argument string is built from a
`$var`, a `${cmd ...}` inline subshell, or an `out:` / `err:`
function call, an attacker who controls that value gains
arbitrary murex (and therefore arbitrary process) execution.

Murex string quoting:
  '...'        — literal single-quoted string, no expansion
  (...)        — literal parens-quoted string, no expansion
  %(...)       — literal percent-paren string, no expansion
  "..."        — interpolating double-quoted string, expands
                 $var and ${command ...}
Murex also has a `command` builtin and a `builtin` builtin that
can prefix any other builtin to bypass user-defined functions of
the same name; we flag the `command eval` / `builtin eval`
prefix forms too.

What this flags
---------------
* `eval $var`                    (bare $var argument)
* `eval "echo $name"`            (double-quoted interpolation)
* `eval "${cat /tmp/x}"`         (murex inline subshell)
* `command eval $x`              (command-prefix bypass form)
* `builtin eval $x`              (builtin-prefix bypass form)
* `eval` at command position (start of line, after `;`, `|`, `&`,
  `(`, `{`, or after the keywords `then` / `else` / `do`)

What this does NOT flag
-----------------------
* `eval 'literal single-quoted code'`  (single quotes are inert)
* `eval (literal parens-quoted code)`  (parens-quoting is inert)
* `eval %(literal percent-quoted)`     (%() quoting is inert)
* `eval echo hello`                    (no `$` or `${`)
* Lines marked with a trailing `# eval-ok` suppression comment

Usage
-----
    python3 detect.py <file_or_dir> [...]

Exit code 1 if any findings, 0 otherwise. python3 stdlib only.
Recurses directories looking for *.mx and *.murex files plus any
file whose first line is a `#!.../murex` shebang.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


# `eval` (optionally prefixed by `command` or `builtin`) at
# command position: start of line (after optional whitespace),
# after `;`, `|`, `&`, `(`, `{`, or after the keywords
# `then` / `else` / `do`.
RE_EVAL = re.compile(
    r"(?:^|(?<=[;|&({])|(?<=\bthen\s)|(?<=\belse\s)|(?<=\bdo\s))"
    r"\s*(?:(?:command|builtin)\s+)?eval\b([^\n]*)"
)

# Suppression marker.
RE_SUPPRESS = re.compile(r"#\s*eval-ok\b")

# Anything that makes the argument dynamic after string scrubbing:
#   $    parameter expansion ($var) or murex ${cmd} inline subshell
RE_DYNAMIC = re.compile(r"\$")


def strip_comments_and_strings(line: str) -> str:
    """Blank `#`-comment tails and the *contents* of all murex
    literal-string forms (`'...'`, `(...)`, `%(...)`), while
    keeping `$` characters that appear inside double-quoted
    strings (which DO interpolate in murex).

    Column positions are preserved.

    Quoting rules implemented
    -------------------------
    * `#` at start-of-token starts a comment to EOL.
    * `'...'` is fully literal.
    * `"..."` interpolates: keep `$` so we still see hazards.
    * `(...)` is murex parens-quoted literal — but parens are
      *also* used as block delimiters in `if (cond) { ... }`
      style. To keep this scrubber syntactically simple we only
      treat parens-quoting as literal when the `(` is preceded by
      whitespace and followed by something other than the murex
      operators that would make it a grouping. In the eval-arg
      position that simplification is safe enough for this
      detector's intent (catching dynamic strings); failure mode
      is an under-flag, not over-flag. Operators that explicitly
      mean "not a string": `=` `!` `<` `>` (rare in eval args).
    * `%(...)` is murex percent-paren-quoted literal.
    """
    out: list[str] = []
    i = 0
    n = len(line)
    in_sq = False
    in_dq = False
    in_pq = False        # ( ... ) parens-quoted
    in_pcpq = False      # %( ... ) percent-paren-quoted
    pq_depth = 0
    while i < n:
        ch = line[i]
        if not in_sq and not in_dq and not in_pq and not in_pcpq:
            # Comment start.
            if ch == "#" and (
                i == 0 or line[i - 1].isspace() or line[i - 1] in ";|&({"
            ):
                out.append(" " * (n - i))
                break
            # %(...) percent-paren-quoted literal.
            if ch == "%" and i + 1 < n and line[i + 1] == "(":
                out.append("  ")
                in_pcpq = True
                pq_depth = 1
                i += 2
                continue
            # (...) parens-quoted literal — only when preceded by
            # whitespace (or start-of-line) and not part of an
            # operator. Inside the eval argument position this is
            # the common shape `eval (some literal code)`.
            if ch == "(" and (i == 0 or line[i - 1].isspace()):
                out.append("(")
                in_pq = True
                pq_depth = 1
                i += 1
                continue
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
            if ch == "'":
                in_sq = False
                out.append(ch)
                i += 1
                continue
            out.append(" ")
            i += 1
            continue
        if in_dq:
            if ch == "\\" and i + 1 < n:
                out.append("  ")
                i += 2
                continue
            if ch == '"':
                in_dq = False
                out.append(ch)
                i += 1
                continue
            if ch == "$":
                out.append(ch)
                i += 1
                continue
            out.append(" ")
            i += 1
            continue
        if in_pq:
            if ch == "(":
                pq_depth += 1
                out.append(" ")
                i += 1
                continue
            if ch == ")":
                pq_depth -= 1
                if pq_depth == 0:
                    in_pq = False
                    out.append(")")
                else:
                    out.append(" ")
                i += 1
                continue
            out.append(" ")
            i += 1
            continue
        # in_pcpq
        if ch == "(":
            pq_depth += 1
            out.append(" ")
            i += 1
            continue
        if ch == ")":
            pq_depth -= 1
            if pq_depth == 0:
                in_pcpq = False
                out.append(")")
            else:
                out.append(" ")
            i += 1
            continue
        out.append(" ")
        i += 1
    return "".join(out)


def is_murex_file(path: Path) -> bool:
    if path.suffix in (".mx", ".murex"):
        return True
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            first = fh.readline()
    except OSError:
        return False
    if not first.startswith("#!"):
        return False
    return "murex" in first


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
            findings.append((path, idx, col, "murex-eval-dynamic", raw.strip()))
    return findings


def iter_targets(roots: list[str]):
    for r in roots:
        p = Path(r)
        if p.is_dir():
            for sub in sorted(p.rglob("*")):
                if sub.is_file() and is_murex_file(sub):
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
