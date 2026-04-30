#!/usr/bin/env python3
"""Detect dangerous Plan 9 `rc` shell `eval` invocations on dynamic strings.

Plan 9's `rc` shell (also packaged as `rc` in plan9port and as the
default shell on 9front) provides an `eval` builtin that joins its
arguments with spaces and re-parses the result as fresh rc source.
Like in POSIX `sh` / `bash` / `zsh`, that becomes a shell-injection
sink the moment any argument is built from a value the script does
not fully control:

* `$var`                  parameter substitution
* `$"var`                 single-string substitution
* `$#var`                 list-length substitution
* `` `{cmd} ``            command substitution (rc spelling — note
                          the braces and the LACK of `$()` in rc)
* `` `cmd ``              older bare-backtick command substitution
* `<{cmd}` / `>{cmd}`     process substitution

`rc` does not have `$(...)`; that is bash/POSIX. So the detector
keys off `$` and backtick on the SAME line as `eval`.

What this flags
---------------
* `eval ANYTHING_WITH_$_OR_BACKTICK`
* `. ANYTHING_WITH_$_OR_BACKTICK`           (rc's `.` builtin
                                             sources a file by name;
                                             a dynamic name is the
                                             classic source-injection
                                             sink, sibling to eval)

Out of scope (deliberately)
---------------------------
* Static `eval 'x=1'` — purely literal, not flagged.
* Calling `rc -c $cmd` — caught by the bash-eval-string detector
  family (the parent shell is what matters there).

Suppress an audited line with a trailing `# eval-ok` comment.

Usage
-----
    python3 detect.py <file_or_dir> [<file_or_dir> ...]

Exit code 1 if any findings, 0 otherwise. python3 stdlib only.
Recurses into directories looking for *.rc files and any file whose
first line is an rc shebang (`#!/usr/bin/rc`, `#!/bin/rc`,
`#!/usr/local/plan9/bin/rc`, etc.).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


# `eval` at command position followed by something on the same line.
# rc's command separators are newline, `;`, `&`, `|`, and the
# pipe-tee `|[fd]`. We also accept it after `if not`, `while`,
# `for(...)`, `switch(...)`, `{`, and `}`.
RE_EVAL = re.compile(
    r"(?:^|(?<=[;&|`{}(])|(?<=\bif\s)|(?<=\bnot\s)|(?<=\bwhile\s))"
    r"\s*\beval\b([^\n]*)"
)

# `.` (rc dot) — sources a file. A dynamic path is rc's source-
# injection sink. Must be at command position; `.` inside a number
# or a hostname must be ignored, so we require it to be either at
# start-of-line / after a separator AND followed by whitespace.
RE_DOT = re.compile(
    r"(?:^|(?<=[;&|`{}(]))"
    r"\s*\.\s+([^\n]*)"
)

# Suppression marker.
RE_SUPPRESS = re.compile(r"#\s*eval-ok\b")

# Anything that makes the argument dynamic in rc: `$` (variables)
# or `` ` `` (command substitution, both `` `{cmd} `` and bare
# `` `cmd `` forms).
RE_DYNAMIC = re.compile(r"[$`]")


def strip_comments_and_strings(line: str) -> str:
    """Blank out `#`-comment tails and `'...'` literals while keeping
    column positions stable. rc has no double-quoted strings and no
    backslash escapes inside single quotes (a literal `'` is written
    `''`). We keep `$` and backticks visible so the dynamic-argument
    check still works."""
    out: list[str] = []
    i = 0
    n = len(line)
    in_sq = False
    while i < n:
        ch = line[i]
        if not in_sq:
            if ch == "#" and (i == 0 or line[i - 1].isspace() or line[i - 1] in ";&|"):
                out.append(" " * (n - i))
                break
            if ch == "'":
                in_sq = True
                out.append(ch)
                i += 1
                continue
            out.append(ch)
            i += 1
            continue
        # in single-quoted string
        if ch == "'":
            in_sq = False
            out.append(ch)
            i += 1
            continue
        out.append(" ")
        i += 1
    return "".join(out)


def is_rc_file(path: Path) -> bool:
    if path.suffix == ".rc":
        return True
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            first = fh.readline()
    except OSError:
        return False
    if not first.startswith("#!"):
        return False
    # Match `/rc` at end of an interpreter path or `env rc`.
    return bool(re.search(r"(^|/)rc(\s|$)", first)) or "env rc" in first


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
            tok_pos = scrub.find("eval", m.start())
            col = (tok_pos if tok_pos >= 0 else m.start()) + 1
            findings.append((path, idx, col, "rc-eval-dynamic", raw.strip()))
        for m in RE_DOT.finditer(scrub):
            rest = m.group(1)
            if not RE_DYNAMIC.search(rest):
                continue
            tok_pos = scrub.find(".", m.start())
            col = (tok_pos if tok_pos >= 0 else m.start()) + 1
            findings.append((path, idx, col, "rc-dot-dynamic", raw.strip()))
    return findings


def iter_targets(roots: list[str]):
    for r in roots:
        p = Path(r)
        if p.is_dir():
            for sub in sorted(p.rglob("*")):
                if sub.is_file() and is_rc_file(sub):
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
