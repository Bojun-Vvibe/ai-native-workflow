#!/usr/bin/env python3
"""Detect bash/sh `eval` invocations on dynamic strings.

`eval STRING` in bash recompiles its argument as shell source and
executes it in the current shell. Any variable, command substitution,
or user-controlled fragment that flows into `eval` is a code-injection
vector equivalent to `system($USER_INPUT)`.

LLM-emitted shell scripts frequently reach for `eval` to "expand a
variable that holds a command" — almost always the wrong tool (arrays,
`"$@"`, or `bash -c --` are the safe alternatives).

What this flags
---------------
A bare `eval` token at statement position whose argument is anything
*other than* an empty/no-op constant. Specifically:

* `eval "$cmd"`            — variable expansion, UNSAFE
* `eval $cmd`              — unquoted, even worse
* `eval "$(...)"`          — command substitution into eval, UNSAFE
* `eval `...``             — backtick command substitution, UNSAFE
* `eval "do_thing $arg"`   — interpolated string, UNSAFE
* `eval 'literal string'`  — single-quoted literal, still flagged
                              (low-risk but rarely justified;
                              suppress with `# eval-ok` on the line
                              if intentional)

Out of scope (deliberately)
---------------------------
* `set -- $(eval echo $x)` style — the inner `eval` is still flagged.
* `[ "$(eval echo $x)" = ... ]` — same, the inner `eval` is flagged.
* We do not try to prove the argument is constant — string-eval with
  no interpolation is still a smell worth a human glance.

Usage
-----
    python3 detect.py <file_or_dir> [<file_or_dir> ...]

Exit code 1 if any findings, 0 otherwise. python3 stdlib only.
Recurses into directories looking for *.sh, *.bash, and files whose
first line is a bash/sh shebang.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


# Match a bareword `eval` at statement position. "Statement position"
# means: start-of-line (after optional whitespace), or after one of
# `;`, `&&`, `||`, `|`, `(`, `{`, `then`, `else`, `do`, `;;`. Followed
# by whitespace and at least one more non-whitespace char (the argument).
RE_EVAL = re.compile(
    r"(?:^|(?<=[;&|({])|(?<=\bthen\s)|(?<=\belse\s)|(?<=\bdo\s)|(?<=;;\s))"
    r"\s*\beval\b\s+(\S)"
)

# A line we suppress: trailing `# eval-ok` marker.
RE_SUPPRESS = re.compile(r"#\s*eval-ok\b")


def strip_comments_and_strings(line: str) -> str:
    """Blank out '...' and "..." string contents and trailing `#` comments,
    preserving column positions. We keep quote characters themselves so
    column-based regexes still see the structural shape."""
    out: list[str] = []
    i = 0
    n = len(line)
    in_s: str | None = None  # None | "'" | '"'
    while i < n:
        ch = line[i]
        if in_s is None:
            if ch == "#":
                # `#` only starts a comment at start-of-line or after whitespace.
                if i == 0 or line[i - 1].isspace():
                    out.append(" " * (n - i))
                    break
                out.append(ch)
                i += 1
                continue
            if ch == "'" or ch == '"':
                in_s = ch
                out.append(ch)
                i += 1
                continue
            out.append(ch)
            i += 1
            continue
        # inside a string
        if ch == "\\" and in_s == '"' and i + 1 < n:
            out.append("  ")
            i += 2
            continue
        if ch == in_s:
            out.append(ch)
            in_s = None
            i += 1
            continue
        out.append(" ")
        i += 1
    return "".join(out)


def is_shell_file(path: Path) -> bool:
    if path.suffix in (".sh", ".bash", ".zsh"):
        return True
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            first = fh.readline()
    except OSError:
        return False
    if not first.startswith("#!"):
        return False
    return any(tok in first for tok in ("bash", "/sh", "zsh", "ksh", "dash"))


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
                (path, idx, m.start() + 1, "eval-string", raw.strip())
            )
    return findings


def iter_targets(roots: list[str]):
    for r in roots:
        p = Path(r)
        if p.is_dir():
            for sub in sorted(p.rglob("*")):
                if sub.is_file() and is_shell_file(sub):
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
