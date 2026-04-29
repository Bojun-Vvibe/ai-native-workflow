#!/usr/bin/env python3
"""Detect dangerous Zsh `eval` invocations on dynamic strings.

In Zsh, `eval ARG...` concatenates its arguments and re-parses the
result as a fresh chunk of shell source. When ARG is built from a
parameter (`$x`, `${x}`, `"$x"`, `$(cmd)`, `` `cmd` ``), an attacker
who controls that value gets full shell execution in the current
shell — exactly the classic shell-injection sink. Zsh adds a few
sharper edges than POSIX `sh`:

* `eval "alias foo=$user"`               — alias body is re-parsed
* `eval "$ZSH_ARGZERO $opts"`            — re-exec with attacker opts
* `print -z $cmd`                        — pushes onto the editor
                                            buffer; harmless until the
                                            user hits return, but in
                                            interactive scripts it is
                                            equivalent to eval
* `: ${(e)var}`                          — the `(e)` parameter
                                            expansion flag forces a
                                            second eval pass on the
                                            value — same blast radius
                                            as bare `eval`

This detector flags the **dynamic** forms. A purely literal
`eval 'set -- a b c'` (no `$`, no `` ` ``, no `$(...)`) is NOT
flagged.

What this flags
---------------
* `eval ANYTHING_WITH_$_OR_BACKTICK_OR_DOLLARPAREN`
* `print -z ANYTHING_WITH_$_OR_BACKTICK_OR_DOLLARPAREN`
* `${(e)var}` parameter expansion (always — the (e) flag itself is
  the danger)

Out of scope (deliberately)
---------------------------
* `source` / `.` of a dynamic path — different sink, sibling
  detector.
* `zsh -c "$cmd"` — caught by the bash-eval-string detector family.
* Building shell command strings to hand to `system(3)` from C — not
  a zsh source-level concern.

Suppress an audited line with a trailing `# eval-ok` comment.

Usage
-----
    python3 detect.py <file_or_dir> [<file_or_dir> ...]

Exit code 1 if any findings, 0 otherwise. python3 stdlib only.
Recurses into directories looking for *.zsh, *.zshrc, *.zshenv,
*.zprofile, *.zlogin, *.zlogout, and files whose first line is a
zsh shebang.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


# `eval` at command position followed by something that contains a
# parameter / command-substitution metacharacter on the SAME line.
RE_EVAL = re.compile(
    r"(?:^|(?<=[;&|`(])|(?<=\bthen\s)|(?<=\belse\s)|(?<=\bdo\s))"
    r"\s*\beval\b([^\n]*)"
)

# `print -z ...` — pushes onto the line editor buffer; equivalent to
# eval once the user hits return. Flag dynamic forms only.
RE_PRINT_Z = re.compile(
    r"(?:^|(?<=[;&|`(])|(?<=\bthen\s)|(?<=\belse\s)|(?<=\bdo\s))"
    r"\s*\bprint\b\s+-z\b([^\n]*)"
)

# `${(e)...}` — the (e) parameter-expansion flag forces a second eval
# pass on the parameter's value. Always dangerous on attacker-influ-
# enced data; we flag every occurrence and let the user suppress.
RE_PAREXP_E = re.compile(r"\$\{\([^)]*\be\b[^)]*\)[^}]*\}")

# Suppression marker.
RE_SUPPRESS = re.compile(r"#\s*eval-ok\b")

# Anything that makes the argument dynamic. After string-content
# scrubbing we cannot rely on the character that immediately follows
# `$` still being there, so a bare `$` or `` ` `` is sufficient
# evidence of a parameter / command substitution.
RE_DYNAMIC = re.compile(r"[$`]")


def strip_comments_and_strings(line: str) -> str:
    """Blank out `#`-comment tails, `'...'` literals, and the
    *contents* (not the delimiters) of `"..."` strings, while keeping
    column positions stable. We intentionally preserve `$`, backticks,
    and `$(...)` that occur OUTSIDE of single quotes, because those
    are the dangerous patterns we want to detect for `eval`. So when
    inside a `"..."` we still keep `$` / `` ` `` visible — that mirrors
    the shell's own behaviour (double quotes do NOT prevent expansion).
    """
    out: list[str] = []
    i = 0
    n = len(line)
    in_sq = False
    in_dq = False
    while i < n:
        ch = line[i]
        if not in_sq and not in_dq:
            if ch == "#" and (i == 0 or line[i - 1].isspace() or line[i - 1] in ";&|"):
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
            if ch == "'":
                in_sq = False
                out.append(ch)
                i += 1
                continue
            # blank single-quoted contents
            out.append(" ")
            i += 1
            continue
        # in_dq: keep $, `, $(, but blank ordinary text so we don't
        # match the literal word "eval" embedded in prose. Easiest:
        # keep dollar-sign and backtick verbatim, blank the rest.
        if ch == "\\" and i + 1 < n:
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
        if ch == "(" and i > 0 and line[i - 1] == "$":
            out.append(ch)
            i += 1
            continue
        out.append(" ")
        i += 1
    return "".join(out)


def is_zsh_file(path: Path) -> bool:
    if path.suffix in (".zsh",):
        return True
    if path.name in (".zshrc", ".zshenv", ".zprofile", ".zlogin", ".zlogout",
                     "zshrc", "zshenv", "zprofile", "zlogin", "zlogout"):
        return True
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            first = fh.readline()
    except OSError:
        return False
    if not first.startswith("#!"):
        return False
    return "zsh" in first


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
            findings.append((path, idx, col, "zsh-eval-dynamic", raw.strip()))
        for m in RE_PRINT_Z.finditer(scrub):
            rest = m.group(1)
            if not RE_DYNAMIC.search(rest):
                continue
            tok_pos = scrub.find("print", m.start())
            col = (tok_pos if tok_pos >= 0 else m.start()) + 1
            findings.append((path, idx, col, "zsh-print-z-dynamic", raw.strip()))
        for m in RE_PAREXP_E.finditer(scrub):
            col = m.start() + 1
            findings.append((path, idx, col, "zsh-parexp-e-flag", raw.strip()))
    return findings


def iter_targets(roots: list[str]):
    for r in roots:
        p = Path(r)
        if p.is_dir():
            for sub in sorted(p.rglob("*")):
                if sub.is_file() and is_zsh_file(sub):
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
