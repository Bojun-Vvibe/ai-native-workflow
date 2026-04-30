#!/usr/bin/env python3
"""Detect dangerous Oil/OSH `eval` invocations on dynamic data.

Oil (now packaged as oils-for-unix; OSH is its bash-compatible
language, YSH its new language) ships an `eval` builtin that, like
every other Bourne descendant, concatenates its string arguments
with spaces and re-parses them as shell input. When any argument
is built from a `$var` / `${var}`, a `$(cmd)` command
substitution, or a backtick `` `cmd` `` substitution, an attacker
who controls that value gains arbitrary shell execution.

Oil also exposes the YSH variant `eval (myblock)` which takes a
*block literal* — that form is structurally safe and we do not
flag it. Likewise `eval $'literal C-string'` (Oil supports
`$'...'`) is treated as a literal because POSIX `$'...'` only
processes backslash escapes, not parameter expansion.

The `command` builtin can prefix `eval` to bypass any shell
function named `eval` (`command eval ...`); we flag that prefix
form too.

What this flags
---------------
* `eval $var` / `eval ${var}` / `eval "${var:-x}"`
* `eval "$(cmd)"`             (POSIX command substitution)
* `eval `cmd``                (legacy backtick form)
* `eval "prefix $x suffix"`   (POSIX double quotes interpolate `$`)
* `command eval $var`         (`command` prefix bypass form)
* `eval` at command position (start of line, after `;`, `|`, `&&`,
  `||`, `(`, or after `then` / `else` / `do`)

What this does NOT flag
-----------------------
* `eval 'literal single-quoted string'` (POSIX single quotes are
  inert — no expansion of any kind)
* `eval $'C-string\\n'`        (POSIX/Oil C-strings only process
  backslash escapes, never `$var` or `$(...)`)
* `eval r'raw string'`         (Oil raw string literal)
* `eval (myblock)`             (YSH block-literal form; parens
  not strings)
* `eval echo hello`           (no `$`, no `$(`, no backtick)
* Lines marked with a trailing `# eval-ok` suppression comment

Usage
-----
    python3 detect.py <file_or_dir> [...]

Exit code 1 if any findings, 0 otherwise. python3 stdlib only.
Recurses directories looking for *.osh and *.ysh files plus any
file whose first line is a `#!.../osh`, `#!.../ysh`, or
`#!.../oil` shebang.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


# `eval` (optionally prefixed by `command`) at command position:
# start of line (after optional whitespace), after `;`, `|`, `&`,
# `(`, or after the keywords `then` / `else` / `do`.
RE_EVAL = re.compile(
    r"(?:^|(?<=[;|&(])|(?<=\bthen\s)|(?<=\belse\s)|(?<=\bdo\s))"
    r"\s*(?:command\s+)?eval\b([^\n]*)"
)

# Suppression marker.
RE_SUPPRESS = re.compile(r"#\s*eval-ok\b")

# Anything that makes the argument dynamic after string scrubbing:
#   $   parameter expansion or $(...) command substitution
#   `   backtick command substitution
RE_DYNAMIC = re.compile(r"[$`]")

# YSH block-literal eval: `eval (` immediately after the keyword
# (with optional whitespace). Block literals are not strings, so
# they don't carry the eval-string hazard.
RE_BLOCK_FORM = re.compile(r"^\s*\(")


def strip_comments_and_strings(line: str) -> str:
    """Blank `#`-comment tails and the *contents* of single-quoted
    POSIX strings (including Oil's `$'...'` C-string and `r'...'`
    raw-string forms — both treat their body as a literal w.r.t.
    `$` expansion), while keeping `$` and `` ` `` characters that
    appear inside double-quoted strings.

    Column positions are preserved.
    """
    out: list[str] = []
    i = 0
    n = len(line)
    in_sq = False  # POSIX or $'' or r'' — all literal w.r.t. $
    in_dq = False
    while i < n:
        ch = line[i]
        if not in_sq and not in_dq:
            # POSIX comments: `#` only at start of word.
            if ch == "#" and (
                i == 0 or line[i - 1].isspace() or line[i - 1] in ";|&("
            ):
                out.append(" " * (n - i))
                break
            # Oil $'...' C-string and r'...' raw-string both open a
            # literal-with-respect-to-$ region. Treat the leading
            # `$` or `r` as plain text and switch to in_sq when the
            # next char is `'`.
            if ch in "$r" and i + 1 < n and line[i + 1] == "'":
                out.append(" ")  # blank the prefix so we don't fake-trigger DYNAMIC
                out.append("'")
                in_sq = True
                i += 2
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
            # POSIX single quotes: no escapes — only the next `'`
            # ends the string. (Oil's $'...' does process \n, \t,
            # etc. but never $var, so for our purpose treating it
            # like a POSIX single-quoted string is safe.)
            if ch == "'":
                in_sq = False
                out.append(ch)
                i += 1
                continue
            out.append(" ")
            i += 1
            continue
        # in_dq: keep `$` and `` ` `` so dangerous interpolation is
        # still visible. Blank everything else.
        if ch == "\\" and i + 1 < n:
            # Inside dq, `\` only escapes `$ " \ <newline>` and
            # `` ` ``. Blank both chars; this avoids a false `$`
            # survivor on `\$literal`.
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


def is_oil_file(path: Path) -> bool:
    if path.suffix in (".osh", ".ysh", ".oil"):
        return True
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            first = fh.readline()
    except OSError:
        return False
    if not first.startswith("#!"):
        return False
    return any(tag in first for tag in ("osh", "ysh", "oil"))


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
            # YSH block-literal form: `eval (myblock)` — skip.
            if RE_BLOCK_FORM.match(rest):
                continue
            if not RE_DYNAMIC.search(rest):
                continue
            tok_pos = m.start()
            while tok_pos < len(scrub) and scrub[tok_pos].isspace():
                tok_pos += 1
            col = tok_pos + 1
            findings.append((path, idx, col, "oil-eval-dynamic", raw.strip()))
    return findings


def iter_targets(roots: list[str]):
    for r in roots:
        p = Path(r)
        if p.is_dir():
            for sub in sorted(p.rglob("*")):
                if sub.is_file() and is_oil_file(sub):
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
