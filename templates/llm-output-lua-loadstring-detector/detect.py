#!/usr/bin/env python3
"""Detect Lua dynamic-code execution sinks: `loadstring`, `load`, `dostring`.

In Lua, `loadstring(s)` (5.1) and `load(s)` (5.2+, when given a string)
compile arbitrary source text into a callable chunk; calling it then
executes that source in the current Lua state. Any value that flows
from input or from string concatenation into these functions is a
code-injection sink equivalent to `system($USER_INPUT)`.

LLM-emitted Lua reaches for `loadstring` / `load` to "evaluate an
expression the user typed" or "build a function from a template
string" — almost always wrong. Safe alternatives:

  * a small interpreter / dispatch table over allowed operations,
  * a sandboxed environment via `setfenv` (5.1) / `_ENV` (5.2+) plus
    a whitelisted function table,
  * pre-compiled functions chosen at runtime by name.

What this flags
---------------
A bareword call to `loadstring(`, `load(`, or `:dostring(` (the
LuaSocket / LuaJIT-style method form). The string-form of `load(...)`
is what's dangerous; `load(function() ... end)` (the reader-function
form) is also flagged because the detector cannot prove the argument
type without parsing — suppress with a trailing `-- loadstring-ok`
comment after audit.

Also flagged:

  * `assert(loadstring(s))()` — wrapped call, still flagged on the
    inner `loadstring`.
  * `local f = load("return " .. expr)` — concatenation into `load`.
  * `dofile` and `loadfile` are NOT flagged here (they read from a
    path, not from an in-memory dynamic string); a separate detector
    can target those.

Out of scope
------------
* Proving the argument is a constant literal — `loadstring("return 1")`
  is still flagged because the smell is the API itself.
* Static-analysis of the surrounding sandbox — even sandboxed
  `loadstring` is worth a human glance.

Usage
-----
    python3 detect.py <file_or_dir> [<file_or_dir> ...]

Exit code 1 if any findings, 0 otherwise. python3 stdlib only.
Recurses into directories looking for *.lua and files whose first
line is a Lua shebang.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


# Match a Lua dynamic-code call. Any of:
#   loadstring(           -- 5.1 / LuaJIT
#   load(                 -- 5.2+ string form
#   :dostring(            -- LuaSocket / some bindings
# Must be at "call position": preceded by start-of-line, whitespace,
# `(`, `,`, `=`, `{`, `[`, or one of the operators `+-*/.`.
RE_DYN = re.compile(
    r"(?:"
    r"(?:^|(?<=[\s(,={\[+\-*/.;]))(loadstring|load)\s*\("
    r"|"
    r"(:dostring)\s*\("
    r")"
)

# Suppress an audited line.
RE_SUPPRESS = re.compile(r"--\s*loadstring-ok\b")


def strip_comments_and_strings(line: str) -> str:
    """Blank out Lua string contents and trailing `--` comments,
    preserving column positions. Handles short strings ('...', "...")
    and `--` line comments. Long brackets ([[ ... ]]) are not multi-
    line-tracked here; if they appear single-line we mask them too.
    """
    out: list[str] = []
    i = 0
    n = len(line)
    in_s: str | None = None  # None | "'" | '"'
    while i < n:
        ch = line[i]
        if in_s is None:
            # `--` line comment (but not `---` doc — same effect)
            if ch == "-" and i + 1 < n and line[i + 1] == "-":
                # mask rest of line as spaces (preserves columns)
                out.append(" " * (n - i))
                break
            # short-string start
            if ch == "'" or ch == '"':
                in_s = ch
                out.append(ch)
                i += 1
                continue
            # single-line long bracket [[...]]
            if ch == "[" and i + 1 < n and line[i + 1] == "[":
                end = line.find("]]", i + 2)
                if end != -1:
                    out.append("[[")
                    out.append(" " * (end - i - 2))
                    out.append("]]")
                    i = end + 2
                    continue
            out.append(ch)
            i += 1
            continue
        # inside a short string
        if ch == "\\" and i + 1 < n:
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


def is_lua_file(path: Path) -> bool:
    if path.suffix == ".lua":
        return True
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            first = fh.readline()
    except OSError:
        return False
    if not first.startswith("#!"):
        return False
    return "lua" in first


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
        for m in RE_DYN.finditer(scrub):
            col = m.start(1) + 1 if m.group(1) else m.start(2) + 1
            findings.append(
                (path, idx, col, "lua-loadstring", raw.strip())
            )
    return findings


def iter_targets(roots: list[str]):
    for r in roots:
        p = Path(r)
        if p.is_dir():
            for sub in sorted(p.rglob("*")):
                if sub.is_file() and is_lua_file(sub):
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
