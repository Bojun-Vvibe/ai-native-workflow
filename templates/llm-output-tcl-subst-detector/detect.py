#!/usr/bin/env python3
"""Detect dangerous Tcl `subst` invocations.

In Tcl, `subst ?-nobackslashes? ?-nocommands? ?-novariables? STRING`
performs backslash, command, and variable substitution on STRING and
returns the result. By default — i.e. with NO flags — `subst $x` is
equivalent to `eval "return \\"$x\\""`: any `[cmd]` substring inside
$x will be executed, and any `$var` will be interpolated. That makes
plain `subst $user_input` a code-injection sink with the same blast
radius as `eval`.

The safe forms are:

* `subst -nocommands -novariables $x`  — text-only template expansion
* `subst -nocommands $x`               — variables only, no command exec
* `format` / `string map`              — when you don't need substitution

LLM-emitted Tcl reaches for `subst` to "expand a template" without
realizing that the default flags leave `[exec ...]` interpolation
fully enabled.

What this flags
---------------
A bareword `subst` token at command position whose flag list does
NOT include `-nocommands`. (We require `-nocommands` because that is
the flag that disables the code-execution branch; `-novariables`
alone still allows `[cmd]` substitution.)

* `subst $tmpl`                          — flagged
* `subst "$header\\n$body"`              — flagged
* `subst -nobackslashes $tmpl`           — flagged (still execs `[..]`)
* `subst -novariables $tmpl`             — flagged (still execs `[..]`)
* `subst -nocommands $tmpl`              — NOT flagged (vars only)
* `subst -nocommands -novariables $tmpl` — NOT flagged (literal)
* `subst -nocommands -novariables -nobackslashes $tmpl` — NOT flagged

"Command position" in Tcl means: start-of-line (after optional
whitespace), or after `;`, `[`, `{`, or `then`/`else` keywords inside
an `if`/`while` body.

Out of scope (deliberately)
---------------------------
* `eval`, `uplevel`, `interp eval` — different (also dangerous)
  constructs, covered by sibling detectors.
* `regsub` with a substitution body that contains `[..]` — different
  semantics, out of scope.
* We do not try to prove the argument is constant.

Suppress an audited line with a trailing `;# subst-ok` (or
`# subst-ok`) comment.

Usage
-----
    python3 detect.py <file_or_dir> [<file_or_dir> ...]

Exit code 1 if any findings, 0 otherwise. python3 stdlib only.
Recurses into directories looking for *.tcl, *.tk, *.itcl, *.exp,
and files whose first line is a tclsh/wish/expect shebang.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


# Match a bareword `subst` token at command position. Capture the rest
# of the line so we can inspect the flag list.
RE_SUBST = re.compile(
    r"(?:^|(?<=[;\[{])|(?<=\bthen\s)|(?<=\belse\s))"
    r"\s*\bsubst\b([^\n]*)"
)

# Suppression marker.
RE_SUPPRESS = re.compile(r"#\s*subst-ok\b")


def strip_comments_and_strings(line: str) -> str:
    """Blank out `"..."` string contents and `#`-comment tail while
    keeping column positions stable. Tcl uses `#` for comments at
    command position only; as a conservative scrubber we treat any
    `#` preceded by whitespace, start-of-line, or `;` as a comment
    start. Braced literals `{...}` are left alone — they are still
    command-position arguments to `subst` and we want to see them."""
    out: list[str] = []
    i = 0
    n = len(line)
    in_dq = False
    while i < n:
        ch = line[i]
        if not in_dq:
            if ch == "#" and (i == 0 or line[i - 1].isspace() or line[i - 1] == ";"):
                out.append(" " * (n - i))
                break
            if ch == '"':
                in_dq = True
                out.append(ch)
                i += 1
                continue
            out.append(ch)
            i += 1
            continue
        # inside double-quoted string
        if ch == "\\" and i + 1 < n:
            out.append("  ")
            i += 2
            continue
        if ch == '"':
            in_dq = False
            out.append(ch)
            i += 1
            continue
        out.append(" ")
        i += 1
    return "".join(out)


def has_nocommands_flag(rest: str) -> bool:
    """Return True iff the leading flag tokens of `rest` (the text
    immediately after the `subst` keyword) include `-nocommands`.

    Tcl's `subst` flags are positional and must precede STRING. We
    walk tokens until we hit something that is not a `-...` flag.
    """
    # Tokens are whitespace-separated. We only look at leading
    # `-`-prefixed tokens (the flag block); STRING starts at the first
    # non-flag token.
    for tok in rest.split():
        if not tok.startswith("-"):
            break
        if tok == "-nocommands":
            return True
    return False


def is_tcl_file(path: Path) -> bool:
    if path.suffix in (".tcl", ".tk", ".itcl", ".exp"):
        return True
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            first = fh.readline()
    except OSError:
        return False
    if not first.startswith("#!"):
        return False
    return any(tok in first for tok in ("tclsh", "wish", "expect"))


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
        for m in RE_SUBST.finditer(scrub):
            rest = m.group(1)
            if has_nocommands_flag(rest):
                continue
            # Find the column of the literal `subst` token within the
            # scrubbed line. m.start() is the start of the leading
            # whitespace; advance to the actual `s` of `subst`.
            tok_pos = scrub.find("subst", m.start())
            col = (tok_pos if tok_pos >= 0 else m.start()) + 1
            findings.append(
                (path, idx, col, "tcl-subst-unsafe", raw.strip())
            )
    return findings


def iter_targets(roots: list[str]):
    for r in roots:
        p = Path(r)
        if p.is_dir():
            for sub in sorted(p.rglob("*")):
                if sub.is_file() and is_tcl_file(sub):
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
