#!/usr/bin/env python3
"""Detect MoonScript dynamic-code execution sinks.

MoonScript compiles to Lua and inherits its dynamic-code surface:

  * loadstring s     -- Lua 5.1 / LuaJIT
  * load s           -- Lua 5.2+ string form
  * obj\\dostring s   -- MoonScript method-call form

Any value flowing from input or concatenation into these functions
is a code-injection sink equivalent to os.execute($USER_INPUT).

What this flags
---------------
A bareword call to ``loadstring`` , ``load`` , or ``\\dostring`` at
call position. Both paren-form ``load(s)`` and MoonScript implicit-
call form ``load s`` are matched.

Suppression
-----------
A trailing ``-- loadstring-ok`` comment on the same line suppresses
the finding on that line.

Out of scope
------------
* ``dofile`` / ``loadfile`` (path-based, separate detector).
* Static argument-type analysis: even ``load("return 1")`` is flagged
  because the smell is the API itself.

Usage
-----
    python3 detect.py <file_or_dir> [<file_or_dir> ...]

Exit code 1 if any findings, 0 otherwise. python3 stdlib only.
Recurses into directories looking for ``*.moon`` and files whose
first line is a MoonScript shebang.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


# Bareword call to loadstring / load. Allow MoonScript implicit-call
# (no parens) too: ``load s`` followed by whitespace + non-operator
# token. To keep the detector simple and conservative, we flag any
# bareword ``loadstring`` or ``load`` at call position followed by
# either ``(`` or whitespace + something that isn't an operator that
# would make it not a call (=, +, -, *, /, etc.).
RE_DYN_PAREN = re.compile(
    r"(?:^|(?<=[\s(,={\[+\-*/.;]))(loadstring|load)\s*\("
)
# Implicit call form: ``loadstring "x"`` or ``load expr``. Require
# at least one whitespace and then a non-operator, non-equals char.
RE_DYN_IMPLICIT = re.compile(
    r"(?:^|(?<=[\s(,={\[+\-*/.;]))(loadstring|load)[ \t]+(?=[\"'(\w])"
)
# MoonScript method form: obj\dostring(...) or obj\dostring "..."
RE_DYN_METHOD = re.compile(
    r"\\(dostring)\s*[(\"' \t]"
)

# Suppress an audited line.
RE_SUPPRESS = re.compile(r"--\s*loadstring-ok\b")


def strip_comments_and_strings(line: str) -> str:
    """Blank out MoonScript string contents and trailing ``--`` comments,
    preserving column positions. Handles short strings and ``--`` line
    comments. Long-bracket strings are not multi-line tracked.
    """
    out: list[str] = []
    i = 0
    n = len(line)
    in_s: str | None = None  # None | "'" | '"'
    while i < n:
        ch = line[i]
        if in_s is None:
            # ``--`` line comment
            if ch == "-" and i + 1 < n and line[i + 1] == "-":
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


def is_moon_file(path: Path) -> bool:
    if path.suffix == ".moon":
        return True
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            first = fh.readline()
    except OSError:
        return False
    if not first.startswith("#!"):
        return False
    return "moon" in first


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
        seen_cols: set[int] = set()
        for m in RE_DYN_PAREN.finditer(scrub):
            col = m.start(1) + 1
            if col in seen_cols:
                continue
            seen_cols.add(col)
            findings.append(
                (path, idx, col, "moonscript-loadstring", raw.strip())
            )
        for m in RE_DYN_IMPLICIT.finditer(scrub):
            col = m.start(1) + 1
            if col in seen_cols:
                continue
            seen_cols.add(col)
            findings.append(
                (path, idx, col, "moonscript-loadstring", raw.strip())
            )
        for m in RE_DYN_METHOD.finditer(scrub):
            col = m.start(1) + 1
            if col in seen_cols:
                continue
            seen_cols.add(col)
            findings.append(
                (path, idx, col, "moonscript-loadstring", raw.strip())
            )
    return findings


def iter_targets(roots: list[str]):
    for r in roots:
        p = Path(r)
        if p.is_dir():
            for sub in sorted(p.rglob("*")):
                if sub.is_file() and is_moon_file(sub):
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
