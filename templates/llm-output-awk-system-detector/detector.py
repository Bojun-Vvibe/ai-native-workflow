#!/usr/bin/env python3
"""Detect risky shell-command sinks in AWK programs.

AWK exposes three ways to hand a string to `/bin/sh`:

* `system(cmd)`              -- run `cmd` synchronously, return exit code
* `cmd | getline var`        -- pipe-from: run `cmd`, read its stdout
* `print ... | cmd`          -- pipe-to:   run `cmd`, write to its stdin

In all three, the right-hand string is evaluated by the shell. When
that string is built from `$1`, `$0`, `ENVIRON[...]`, `ARGV[...]`,
or any field/variable derived from input, this is the AWK form of
`eval(user_input)` -- a classic command-injection sink.

LLM-generated awk one-liners reach for `system("rm " $1)` and
`("curl " url) | getline body` constantly. The defensive forms are:

* call `getline` on a *literal* command, never an interpolated one;
* shell out via `xargs -0` / explicit `execve` from a wrapper shell
  rather than letting awk build the command string;
* if you must, single-quote and `gsub(/'/,"'\\''", v)` the value --
  but at that point you no longer want awk for this.

What this flags
---------------
On a per-line basis, after blanking comments and string contents:

| Pattern                              | Kind                  |
| ------------------------------------ | --------------------- |
| `system(<arg>)` where <arg> is not a bare string literal | `awk-system-dynamic` |
| `system(<arg>)` always                                   | `awk-system`         |
| `<expr> | getline ...` where the LHS is not a bare string literal | `awk-getline-pipe-from-dynamic` |
| `print ... | <expr>` where RHS is not a bare string literal       | `awk-print-pipe-to-dynamic`     |

A "bare string literal" means the argument was *only* a `"..."`
constant before scrubbing -- i.e., scrubbing produced an empty pair
of quotes with nothing else.

Out of scope
------------
* `|&` co-process pipes (gawk-specific) -- treated like `|`.
* `printf` to a piped command is handled by the `print` rule (we
  match the `| <expr>` shape, not the `print` keyword).
* We do not try to prove the variable is sanitized.

Suppression: append `# awk-exec-ok` on the line.

Usage
-----
    python3 detector.py <file_or_dir> [<file_or_dir> ...]

Recurses into directories looking for `*.awk`, `*.gawk`, `*.mawk`,
and files whose first line is an awk/gawk/mawk shebang. Exit code 1
if any findings, 0 otherwise. python3 stdlib only.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


RE_SUPPRESS = re.compile(r"#\s*awk-exec-ok\b")

# system( ARG ) -- capture the argument span (no nested parens
# expected in typical awk; we stop at the first matching `)` on the
# same line, after scrubbing strings).
RE_SYSTEM = re.compile(r"\bsystem\s*\(([^()]*)\)")

# X | getline  (also captures `|&`)
# We require `getline` token after the pipe, possibly with a target.
RE_PIPE_FROM = re.compile(r"([^\s|][^|]*?)\|\&?\s*getline\b")

# print ... | X   or   printf ... | X
# We capture the RHS up to end-of-line (after scrubbing).
RE_PIPE_TO = re.compile(r"\b(?:print|printf)\b[^|\n]*\|\&?\s*(.+?)\s*$")


def strip_comments_and_strings(line: str) -> str:
    """Blank out `"..."` string contents and `#` comments. AWK uses
    only double-quoted strings (single quotes are not a string
    delimiter in awk). Backslash escapes inside strings are honored.
    `#` is always a comment start outside a string."""
    out: list[str] = []
    i = 0
    n = len(line)
    in_dq = False
    while i < n:
        ch = line[i]
        if not in_dq:
            if ch == "#":
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


def is_bare_string_literal(scrubbed_arg: str) -> bool:
    """After scrubbing, a pure `"..."` literal becomes `"  ...  "`
    (quotes preserved, contents blanked). So "bare literal" means
    the only non-space chars are the two quotes."""
    s = scrubbed_arg.strip()
    if len(s) < 2:
        return False
    if s[0] != '"' or s[-1] != '"':
        return False
    inner = s[1:-1]
    return inner.strip() == ""


def is_awk_file(path: Path) -> bool:
    if path.suffix in (".awk", ".gawk", ".mawk"):
        return True
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            first = fh.readline()
    except OSError:
        return False
    if not first.startswith("#!"):
        return False
    return any(tok in first for tok in ("awk", "gawk", "mawk"))


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
        for m in RE_SYSTEM.finditer(scrub):
            arg = m.group(1)
            kind = "awk-system" if is_bare_string_literal(arg) else "awk-system-dynamic"
            findings.append((path, idx, m.start() + 1, kind, raw.strip()))
        for m in RE_PIPE_FROM.finditer(scrub):
            lhs = m.group(1)
            if is_bare_string_literal(lhs):
                continue
            findings.append(
                (path, idx, m.start() + 1, "awk-getline-pipe-from-dynamic", raw.strip())
            )
        for m in RE_PIPE_TO.finditer(scrub):
            rhs = m.group(1)
            if is_bare_string_literal(rhs):
                continue
            findings.append(
                (path, idx, m.start() + 1, "awk-print-pipe-to-dynamic", raw.strip())
            )
    return findings


def iter_targets(roots: list[str]):
    for r in roots:
        p = Path(r)
        if p.is_dir():
            for sub in sorted(p.rglob("*")):
                if sub.is_file() and is_awk_file(sub):
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
