#!/usr/bin/env python3
"""Detect Tcl `eval` invocations on dynamic strings.

In Tcl, `eval ARG ?ARG ...?` concatenates its arguments with spaces and
re-parses the result as a Tcl script. Whenever any of those arguments
holds attacker- or user-controlled text, `eval` is a code-injection
sink — semantically the same as `system($USER_INPUT)` in shell.

LLM-emitted Tcl frequently reaches for `eval` to "splice a command that
lives in a variable." That is almost always wrong; the modern, safe
forms are:

* `{*}$cmd_list` (Tcl 8.5+ argument expansion), or
* `command $arg1 $arg2 ...` directly,
* never `eval $cmd`.

What this flags
---------------
A bareword `eval` token at command position. "Command position" in
Tcl means: start-of-line (after optional whitespace), or after `;`,
`[`, `{`, or `then`/`else` keywords inside an `if`/`while` body.

* `eval $cmd`              — variable into eval, UNSAFE
* `eval "$cmd"`            — quoted variable, still UNSAFE
* `eval [foo $x]`          — command-substitution result into eval
* `eval $cmd $arg1 $arg2`  — list-shaped, still flagged
* `eval {literal script}`  — braced-literal eval; low risk but rarely
                              justified, suppress with `;# eval-ok`

Out of scope (deliberately)
---------------------------
* `uplevel`, `subst -nocommands`, `interp eval` — also dangerous but
  out of scope for this single-purpose detector.
* We do not try to prove the argument is constant.

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


# Match a bareword `eval` at command position. Command position:
# start-of-line (after optional whitespace), or after `;`, `[`, `{`,
# or whitespace-bounded `then`/`else` keywords. Followed by whitespace
# and at least one more non-whitespace char (the argument).
RE_EVAL = re.compile(
    r"(?:^|(?<=[;\[{])|(?<=\bthen\s)|(?<=\belse\s))"
    r"\s*\beval\b\s+(\S)"
)

# Suppression marker: `;# eval-ok` or `# eval-ok` on the line.
RE_SUPPRESS = re.compile(r"#\s*eval-ok\b")


def strip_comments_and_strings(line: str) -> str:
    """Blank out "..." string contents and `#` comments while keeping
    column positions stable. Tcl uses `#` for comments only at command
    position, but as a conservative scrubber we treat any `#` preceded
    by whitespace or start-of-line as a comment start. Braced literals
    `{...}` are left alone here (they are still command-position
    arguments to `eval` and we WANT to see them as the argument)."""
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
        for m in RE_EVAL.finditer(scrub):
            findings.append(
                (path, idx, m.start() + 1, "tcl-eval", raw.strip())
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
