#!/usr/bin/env python3
"""Detect CoffeeScript dynamic-code execution sinks.

CoffeeScript compiles to JavaScript and inherits its dynamic-code
surface:

  * eval s                         -- direct or indirect eval
  * new Function s / Function s    -- compile a string to callable
  * vm.runInThisContext s          -- Node vm module
  * setTimeout s, n                -- string first arg => eval
  * setInterval s, n               -- string first arg => eval

Any value flowing from input or concatenation into these is a code-
injection sink equivalent to exec($USER_INPUT).

What this flags
---------------
A bareword call to ``eval`` , ``Function`` , ``new Function`` ,
``vm.runInThisContext`` , or ``setTimeout`` / ``setInterval`` whose
first argument starts with a string literal (``"`` or ``'``).

Both paren-form and CoffeeScript implicit-call form are matched.

Suppression
-----------
A trailing ``# eval-ok`` comment on the same line suppresses the
finding on that line.

Out of scope
------------
* ``require`` (module path, not arbitrary code).
* ``vm.runInNewContext`` (separate detector can target unsandboxed
  forms).

Usage
-----
    python3 detect.py <file_or_dir> [<file_or_dir> ...]

Exit code 1 if any findings, 0 otherwise. python3 stdlib only.
Recurses into directories looking for ``*.coffee`` and files whose
first line is a CoffeeScript shebang.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


# eval(...) or eval s  -- bareword at call position
RE_EVAL = re.compile(
    r"(?:^|(?<=[\s(,=\[+\-*/.;&|!?:]))(eval)(?:\s*\(|[ \t]+(?=[\"'(\w]))"
)
# new Function ... or Function(...) at call position
RE_NEW_FUNCTION = re.compile(
    r"(?:^|(?<=[\s(,=\[+\-*/.;&|!?:]))new\s+(Function)\b"
)
RE_FUNCTION_CALL = re.compile(
    r"(?:^|(?<=[\s(,=\[+\-*/.;&|!?:]))(Function)\s*\("
)
# vm.runInThisContext(...) or vm.runInThisContext "..."
RE_VM_THIS = re.compile(
    r"\bvm\.(runInThisContext)\b"
)
# setTimeout "..." , n  /  setInterval "..." , n  (string first arg)
RE_SETTIMER_STRING = re.compile(
    r"(?:^|(?<=[\s(,=\[+\-*/.;&|!?:]))(setTimeout|setInterval)\s*\(?\s*[\"']"
)

RE_SUPPRESS = re.compile(r"#\s*eval-ok\b")


def strip_comments_and_strings(line: str, state: dict) -> str:
    # Mask CoffeeScript comments (`#` line, `###` block) and string
    # literals (single, double, and triple-quoted). Triple-quoted
    # strings and `###` block comments may span lines; ``state`` is a
    # mutable dict that carries cross-line context. Keys:
    #   ``in_triple`` : None | '"""' | "'''"
    #   ``in_block_c``: bool   (inside ``###`` block comment)
    # Preserves column positions.
    out: list[str] = []
    i = 0
    n = len(line)
    in_s: str | None = None  # single-line short string
    while i < n:
        # Continuing a multi-line state?
        if state.get("in_block_c"):
            # look for closing ``###``
            end = line.find("###", i)
            if end == -1:
                out.append(" " * (n - i))
                return "".join(out)
            out.append(" " * (end + 3 - i))
            i = end + 3
            state["in_block_c"] = False
            continue
        if state.get("in_triple"):
            quote = state["in_triple"]
            end = line.find(quote, i)
            if end == -1:
                out.append(" " * (n - i))
                return "".join(out)
            out.append(" " * (end - i))
            out.append(quote)
            i = end + 3
            state["in_triple"] = None
            continue

        ch = line[i]
        if in_s is None:
            # ``###`` block comment open
            if ch == "#" and line[i:i + 3] == "###":
                state["in_block_c"] = True
                out.append("   ")
                i += 3
                continue
            # ``#`` line comment
            if ch == "#":
                out.append(" " * (n - i))
                break
            # triple-quoted string open
            if line[i:i + 3] == '"""' or line[i:i + 3] == "'''":
                quote = line[i:i + 3]
                state["in_triple"] = quote
                out.append(quote)
                i += 3
                continue
            if ch == "'" or ch == '"':
                in_s = ch
                out.append(ch)
                i += 1
                continue
            out.append(ch)
            i += 1
            continue
        # inside a single-line short string
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


def is_coffee_file(path: Path) -> bool:
    if path.suffix == ".coffee":
        return True
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            first = fh.readline()
    except OSError:
        return False
    if not first.startswith("#!"):
        return False
    return "coffee" in first


def scan_file(path: Path) -> list[tuple[Path, int, int, str, str]]:
    findings: list[tuple[Path, int, int, str, str]] = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return findings
    state: dict = {"in_triple": None, "in_block_c": False}
    for idx, raw in enumerate(text.splitlines(), start=1):
        if RE_SUPPRESS.search(raw):
            # still advance state so multi-line strings stay tracked
            strip_comments_and_strings(raw, state)
            continue
        scrub = strip_comments_and_strings(raw, state)
        seen_cols: set[int] = set()

        def emit(col: int) -> None:
            if col in seen_cols:
                return
            seen_cols.add(col)
            findings.append(
                (path, idx, col, "coffee-eval", raw.strip())
            )

        for m in RE_EVAL.finditer(scrub):
            emit(m.start(1) + 1)
        for m in RE_NEW_FUNCTION.finditer(scrub):
            emit(m.start(1) + 1)
        for m in RE_FUNCTION_CALL.finditer(scrub):
            # Skip if preceded by ``new`` (already counted by RE_NEW_FUNCTION)
            start = m.start(1)
            preceding = scrub[max(0, start - 4):start].rstrip()
            if preceding.endswith("new"):
                continue
            emit(start + 1)
        for m in RE_VM_THIS.finditer(scrub):
            emit(m.start(1) + 1)
        for m in RE_SETTIMER_STRING.finditer(scrub):
            emit(m.start(1) + 1)
    return findings


def iter_targets(roots: list[str]):
    for r in roots:
        p = Path(r)
        if p.is_dir():
            for sub in sorted(p.rglob("*")):
                if sub.is_file() and is_coffee_file(sub):
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
