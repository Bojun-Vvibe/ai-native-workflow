#!/usr/bin/env python3
"""Detect Vim script `:execute` / `eval()` invocations on dynamic strings.

In Vim script, `:execute STR` builds an Ex command from STR and runs it,
and `eval(STR)` parses STR as a Vim script expression and returns its
value. Both are dynamic-code sinks: any caller-controlled fragment
spliced into STR becomes runnable Vim script — same blast radius as
`system($USER_INPUT)` in shell.

LLM-emitted Vim plugins frequently reach for `:execute` to "build a
command from variables" (e.g. `:execute 'normal' a:keys`). The safe
forms are:

* `feedkeys(s, 'n')` for keystroke replay (escapes are explicit), or
* a normal Ex command with literal `<args>` placeholders, or
* `:call` for invoking a known function with arguments.

What this flags
---------------
A bareword `execute` / `exec` / `exe` Ex-command at command position,
and any `eval(` function-call. "Command position" in Vim script means:
start-of-line (after optional whitespace and an optional leading `:`),
or after a `|` command separator.

* `execute 'normal ' . a:keys`   — string concat into execute, UNSAFE
* `exe "edit " . fname`          — short form, still UNSAFE
* `:exec a:cmd`                  — bare variable, UNSAFE
* `let v = eval(a:expr)`         — expression eval, UNSAFE
* `call eval(s:s)`               — same, UNSAFE

Out of scope (deliberately)
---------------------------
* `:source`, `:runtime`, `:luaeval`, `py3eval` — also dangerous but
  out of scope for this single-purpose detector.
* We do not try to prove the argument is constant.

Suppression
-----------
A trailing `" exec-ok` comment on the line suppresses that line.

Usage
-----
    python3 detect.py <file_or_dir> [<file_or_dir> ...]

Exit code 1 if any findings, 0 otherwise. python3 stdlib only.
Recurses into directories looking for *.vim, *.vimrc, and files whose
first line is a `vim:` modeline shebang or `" Vim` header.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


# `execute` / `exec` / `exe` at command position. Command position:
# start-of-line (allowing optional `:` and whitespace), or after `|`.
RE_EXECUTE = re.compile(
    r"(?:^|(?<=\|))\s*:?\s*\b(execute|exec|exe)\b\s+(\S)"
)

# `eval(` function call — dynamic Vim-expression sink.
RE_EVAL = re.compile(r"\beval\s*\(")

# Suppression marker.
RE_SUPPRESS = re.compile(r'"\s*exec-ok\b')


def strip_comments_and_strings(line: str) -> str:
    """Blank out string contents and `"`-comments while keeping column
    positions stable. Vim script uses `"` for both string literals AND
    line comments — a `"` is a comment iff it appears at command
    position (start of an Ex command). To stay simple and conservative
    we treat `"` at start-of-line / after-`|` / after-whitespace-only-
    prefix as a comment; otherwise as a string delimiter. Single-quoted
    strings `'...'` use doubled `''` for an embedded apostrophe."""
    out: list[str] = []
    i = 0
    n = len(line)
    in_sq = False
    in_dq = False
    # Determine if a `"` at this position starts a comment. Rule:
    # everything before it on the line is whitespace or `:` or `|`.
    prefix_is_blank = True
    while i < n:
        ch = line[i]
        if in_sq:
            if ch == "'":
                # doubled '' = literal apostrophe inside the string
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
            out.append(" ")
            i += 1
            continue
        # not in any string
        if ch == '"':
            if prefix_is_blank:
                # comment to end of line
                out.append(" " * (n - i))
                break
            in_dq = True
            out.append(ch)
            i += 1
            prefix_is_blank = False
            continue
        if ch == "'":
            in_sq = True
            out.append(ch)
            i += 1
            prefix_is_blank = False
            continue
        if ch == "|":
            # `|` resets command-position prefix (next token is a new Ex cmd)
            out.append(ch)
            i += 1
            prefix_is_blank = True
            continue
        if not ch.isspace() and ch != ":":
            prefix_is_blank = False
        out.append(ch)
        i += 1
    return "".join(out)


def is_vim_file(path: Path) -> bool:
    if path.suffix in (".vim", ".vimrc"):
        return True
    name = path.name
    if name in ("vimrc", ".vimrc", "_vimrc", "gvimrc", ".gvimrc"):
        return True
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            first = fh.readline()
    except OSError:
        return False
    return "vim:" in first or first.startswith('" Vim')


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
        for m in RE_EXECUTE.finditer(scrub):
            findings.append(
                (path, idx, m.start(1) + 1, "vim-execute", raw.strip())
            )
        for m in RE_EVAL.finditer(scrub):
            findings.append(
                (path, idx, m.start() + 1, "vim-eval", raw.strip())
            )
    return findings


def iter_targets(roots: list[str]):
    for r in roots:
        p = Path(r)
        if p.is_dir():
            for sub in sorted(p.rglob("*")):
                if sub.is_file() and is_vim_file(sub):
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
