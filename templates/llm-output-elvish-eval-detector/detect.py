#!/usr/bin/env python3
"""Detect dangerous Elvish `eval` invocations on dynamic strings.

In Elvish (https://elv.sh), the builtin `eval` accepts a string and
executes it as elvish source in a fresh namespace:

    eval $code
    eval (slurp < script.elv)
    eval "echo "$header

When the argument is built from a variable or a command-substitution
output, an attacker who controls that value gets full elvish-runtime
execution: arbitrary external commands, filesystem writes, env
mutation, etc. The blast radius is identical to `bash eval`, but
Elvish's pipeline-friendly syntax makes the dangerous form especially
easy to write — `eval (curl $url | slurp)` is a one-liner that LLMs
emit when asked for "run a remote installer" code.

What this flags
---------------
* `eval $var`                            — variable expansion
* `eval "..."` containing `$var` / `(cmd)` / `` `cmd` ``
* `eval (cmd ...)`                       — output-capture
* `eval (slurp < $path)`                 — file-driven eval

A purely literal `eval "set-env FOO bar"` (no `$`, no `(`, no
`` ` ``) is NOT flagged.

Out of scope (deliberately)
---------------------------
* `use` with a dynamic module name — different sink, sibling
  detector.
* `e:cmd $arg` — running an external with attacker args is a
  separate (well-known) shell-injection family.
* `src` / `-source` flag of `elvish` invoked from outside Elvish.

Suppress an audited line with a trailing `# eval-ok` comment.

Usage
-----
    python3 detect.py <file_or_dir> [<file_or_dir> ...]

Exit code 1 if any findings, 0 otherwise. python3 stdlib only.
Recurses into directories looking for *.elv and files whose first
line is an elvish shebang.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


# `eval` token at command position. Elvish command position: start of
# line (after optional whitespace), after `;`, after `|`, after `{`,
# or after `(` (subexpression / output-capture).
RE_EVAL = re.compile(
    r"(?:^|(?<=[;|{(])|(?<=\bthen\s)|(?<=\belse\s))"
    r"\s*\beval\b([^\n]*)"
)

# Suppression marker.
RE_SUPPRESS = re.compile(r"#\s*eval-ok\b")

# Anything that makes the argument dynamic. After string-content
# scrubbing we cannot rely on the character that immediately follows
# `$` still being there, so a bare `$` is sufficient evidence of a
# variable expansion. `(` (output capture / subexpression) and
# `` ` `` are also dynamic markers.
RE_DYNAMIC = re.compile(r"[$`(]")


def strip_comments_and_strings(line: str) -> str:
    """Blank out `#`-comment tails and the *contents* of single- and
    double-quoted Elvish string literals while keeping column
    positions stable.

    Elvish quoting:
    * `'...'` — single-quoted, fully literal, `''` is an escaped
      single quote inside. No expansion.
    * `"..."` — double-quoted, supports `\\n` etc. backslash escapes
      but NOT `$var` interpolation. So unlike bash, double quotes in
      elvish are inert with respect to variables.

    Conclusion: contents of BOTH quote styles can be safely blanked
    out — they cannot contain the `$` / `(` we are looking for in a
    way that would be re-evaluated by `eval`. Wait — they CAN contain
    those characters as literal text that, once `eval`'d, becomes
    elvish code. So `eval "echo $x"` IS dangerous: the `$x` becomes
    a real expansion in the second pass. We therefore must NOT blank
    out string contents for the `eval` argument check.

    To balance both concerns we keep `$`, `` ` ``, and `(` characters
    inside `"..."` strings (the only quoting style elvish actually
    re-parses inside `eval`), and fully blank `'...'` literals.
    """
    out: list[str] = []
    i = 0
    n = len(line)
    in_sq = False
    in_dq = False
    while i < n:
        ch = line[i]
        if not in_sq and not in_dq:
            if ch == "#" and (i == 0 or line[i - 1].isspace() or line[i - 1] in ";|{("):
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
            # Elvish single-quote escape is `''`. We don't need to
            # resolve it precisely; just track quote balance.
            if ch == "'":
                # Look ahead: `''` is escaped quote, stay in_sq.
                if i + 1 < n and line[i + 1] == "'":
                    out.append("  ")
                    i += 2
                    continue
                in_sq = False
                out.append(ch)
                i += 1
                continue
            out.append(" ")
            i += 1
            continue
        # in_dq: keep $, `, ( so eval-of-a-double-quoted-string with
        # interpolation markers is still detected. Blank everything
        # else so the literal word "eval" buried in prose does not
        # match.
        if ch == "\\" and i + 1 < n:
            out.append("  ")
            i += 2
            continue
        if ch == '"':
            in_dq = False
            out.append(ch)
            i += 1
            continue
        if ch in "$`(":
            out.append(ch)
            i += 1
            continue
        out.append(" ")
        i += 1
    return "".join(out)


def is_elvish_file(path: Path) -> bool:
    if path.suffix == ".elv":
        return True
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            first = fh.readline()
    except OSError:
        return False
    if not first.startswith("#!"):
        return False
    return "elvish" in first


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
            findings.append((path, idx, col, "elvish-eval-dynamic", raw.strip()))
    return findings


def iter_targets(roots: list[str]):
    for r in roots:
        p = Path(r)
        if p.is_dir():
            for sub in sorted(p.rglob("*")):
                if sub.is_file() and is_elvish_file(sub):
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
