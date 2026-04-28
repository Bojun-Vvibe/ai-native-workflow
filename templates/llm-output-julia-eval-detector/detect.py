#!/usr/bin/env python3
"""Detect Julia dynamic-code execution sinks via `eval` / `Meta.parse`.

In Julia, `eval(ex)` evaluates an `Expr` in the current module, and
`Meta.parse(s)` turns an arbitrary source string into an `Expr`. The
combination — `eval(Meta.parse(user_input))` — or any direct `eval`
on a value built from runtime data is a code-injection sink with the
same blast radius as `system($USER_INPUT)`. `@eval` (the macro form)
has the same effect.

LLM-emitted Julia reaches for `eval` to "build a function from a
template string" or "compute a symbol the user named". Almost always
wrong. Safe alternatives:

  * `getfield(Module, Symbol(name))` for *looking up* a named
    function (still risky if `name` is unconstrained — whitelist),
  * a `Dict{String, Function}` dispatch table,
  * generated functions / multiple dispatch for the type-driven case,
  * `include_string(Main, code)` is *also* dynamic execution and is
    likewise flagged.

What this flags
---------------
A bareword call or macro use of any of:

  * `eval(`              — module-level or imported `eval`
  * `Core.eval(`         — fully-qualified
  * `Base.eval(`         — fully-qualified
  * `@eval`              — macro form, with or without args
  * `Meta.parse(`        — string-to-Expr (almost always paired with eval)
  * `include_string(`    — direct string execution

Also flagged when nested: `eval(Meta.parse(s))` produces two findings.

Out of scope
------------
* `include("file.jl")` — reads a path, not a runtime string. Use a
  separate detector if needed.
* Static-analysis of whether the argument is a constant `Expr` —
  even constant-`Expr` `eval` is worth a human glance.

Usage
-----
    python3 detect.py <file_or_dir> [<file_or_dir> ...]

Exit code 1 if any findings, 0 otherwise. python3 stdlib only.
Recurses into directories looking for *.jl and files whose first
line is a Julia shebang.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


# Function-call sinks: must be at "call position" — preceded by SOL,
# whitespace, `(`, `,`, `=`, `[`, `{`, `;`, or one of `+-*/.|&`.
RE_CALL = re.compile(
    r"(?:^|(?<=[\s(,={\[;+\-*/.|&]))"
    r"(eval|Core\.eval|Base\.eval|Meta\.parse|include_string)\s*\("
)

# Macro sink: `@eval` is a token; require non-identifier (or SOL) before `@`.
RE_MACRO = re.compile(
    r"(?:^|(?<=[\s(,={\[;+\-*/.|&]))(@eval)\b"
)

# Suppress an audited line.
RE_SUPPRESS = re.compile(r"#\s*eval-ok\b")


def strip_comments_and_strings(line: str) -> str:
    """Blank out Julia string contents and trailing `#` line comments,
    preserving column positions. Handles:

      * `#` line comments (mask rest of line)
      * `"..."` short strings (with `\\` escapes)
      * `\"\"\"...\"\"\"` triple-strings on a single line
      * raw `r"..."` and bytestring `b"..."` are treated as `"..."`
      * char literals `'x'` are tiny; we mask conservatively

    Block comments `#= ... =#` that fit on one line are also masked;
    multi-line block comments are not tracked across lines.
    """
    out: list[str] = []
    i = 0
    n = len(line)
    in_s: str | None = None  # None | '"' | '"""'
    while i < n:
        ch = line[i]
        if in_s is None:
            # `#=` block comment, single-line variant
            if ch == "#" and i + 1 < n and line[i + 1] == "=":
                end = line.find("=#", i + 2)
                if end != -1:
                    out.append(" " * (end + 2 - i))
                    i = end + 2
                    continue
                # unterminated on this line: mask to EOL
                out.append(" " * (n - i))
                break
            # `#` line comment
            if ch == "#":
                out.append(" " * (n - i))
                break
            # triple-quoted string start
            if ch == '"' and i + 2 < n and line[i + 1] == '"' and line[i + 2] == '"':
                # find closing """
                end = line.find('"""', i + 3)
                if end != -1:
                    out.append('"""')
                    out.append(" " * (end - i - 3))
                    out.append('"""')
                    i = end + 3
                    continue
                in_s = '"""'
                out.append('"""')
                i += 3
                continue
            if ch == '"':
                in_s = '"'
                out.append(ch)
                i += 1
                continue
            out.append(ch)
            i += 1
            continue
        # inside a short string
        if in_s == '"':
            if ch == "\\" and i + 1 < n:
                out.append("  ")
                i += 2
                continue
            if ch == '"':
                out.append(ch)
                in_s = None
                i += 1
                continue
            out.append(" ")
            i += 1
            continue
        # inside triple string (single line case)
        if in_s == '"""':
            if i + 2 < n and ch == '"' and line[i + 1] == '"' and line[i + 2] == '"':
                out.append('"""')
                in_s = None
                i += 3
                continue
            out.append(" ")
            i += 1
            continue
    return "".join(out)


def is_julia_file(path: Path) -> bool:
    if path.suffix == ".jl":
        return True
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            first = fh.readline()
    except OSError:
        return False
    if not first.startswith("#!"):
        return False
    return "julia" in first


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
        for m in RE_CALL.finditer(scrub):
            findings.append(
                (path, idx, m.start(1) + 1, "julia-eval", raw.strip())
            )
        for m in RE_MACRO.finditer(scrub):
            findings.append(
                (path, idx, m.start(1) + 1, "julia-eval", raw.strip())
            )
    return findings


def iter_targets(roots: list[str]):
    for r in roots:
        p = Path(r)
        if p.is_dir():
            for sub in sorted(p.rglob("*")):
                if sub.is_file() and is_julia_file(sub):
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
