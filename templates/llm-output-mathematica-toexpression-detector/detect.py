#!/usr/bin/env python3
"""Detect Wolfram Language / Mathematica dynamic-code execution sinks.

Wolfram Language has several ways to take a string (or a held
expression) and evaluate it as code, all of which are
code-injection sinks when the input is attacker- or LLM-controlled:

  * ToExpression[s]            -- parses ``s`` as Wolfram source and
                                  evaluates it in the current
                                  context. The canonical "eval a
                                  string" sink.
  * ToExpression[s, fmt]       -- same, with an explicit input
                                  format (InputForm, TeXForm, etc.).
  * ToExpression[s, fmt, head] -- still evaluates; ``head`` only
                                  controls how the result is wrapped.
  * Get[path]  /  << path      -- reads a .m / .wl file and
                                  evaluates it. With a
                                  non-literal path this is
                                  arbitrary code by another name.
                                  ``<<`` is the operator form.
  * Needs[ctx, path]           -- if ``path`` is computed, same
                                  hazard as ``Get``.
  * RunProcess[s] / Run[s]     -- shell out (separate hazard
                                  class, but same root cause when
                                  ``s`` flows from input).

What this flags
---------------
A bareword call to ``ToExpression[`` , ``Get[`` , ``Needs[`` ,
``Run[`` , ``RunProcess[`` , or use of the ``<<`` get-operator
followed by an identifier or string literal.

The detector is single-pass with comment + string-literal masking.
Wolfram comments are ``(* ... *)`` and may nest; strings are
double-quoted with ``\\`` escapes.

Suppression
-----------
A trailing ``(* eval-ok *)`` comment on the same line suppresses
the finding on that line.

Out of scope
------------
* ``Symbol[name]`` — turns a string into a symbol but does not
  evaluate it as source. Separate concern.
* ``Hold`` / ``HoldComplete`` wrappers around ``ToExpression``
  args — these are usually defensive and we still flag the call
  site so a reviewer can confirm.

Usage
-----
    python3 detect.py <file_or_dir> [<file_or_dir> ...]

Exit code 1 if any findings, 0 otherwise. python3 stdlib only.
Recurses into directories looking for ``*.m``, ``*.wl``, ``*.wls``,
and files whose first line is a Wolfram shebang
(``#!/usr/bin/env wolframscript``).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


# Token-boundary helper: previous char must be start, whitespace,
# or one of the Wolfram expression separators.
_WB_PREV = r"(?:^|(?<=[\s;,()\[\]{}=+\-*/&|!?<>@^]))"

RE_TOEXPRESSION = re.compile(_WB_PREV + r"(ToExpression)\s*\[")
RE_GET_FUNC = re.compile(_WB_PREV + r"(Get)\s*\[")
RE_NEEDS_FUNC = re.compile(_WB_PREV + r"(Needs)\s*\[")
RE_RUNPROCESS = re.compile(_WB_PREV + r"(RunProcess)\s*\[")
RE_RUN_FUNC = re.compile(_WB_PREV + r"(Run)\s*\[")
# ``<<`` get-operator: ``<<MyPackage`Sub` `` or ``<< "path/to/file.m"``.
# Must not match left-shift in arithmetic (which would be ``<<`` between
# numeric expressions; Wolfram uses BitShiftLeft, so ``<<`` between
# numbers is rare, but we still require the next token to be an
# identifier, backtick, or string literal).
RE_GET_OP = re.compile(
    _WB_PREV + r"(<<)\s*(?=[A-Za-z_\"`])"
)

RE_SUPPRESS = re.compile(r"\(\*\s*eval-ok\s*\*\)")


def strip_comments_and_strings(line: str, state: dict) -> str:
    """Mask Wolfram ``(* … *)`` (nestable) comments and ``"…"``
    strings. ``state`` carries cross-line context:

      ``depth`` : int   (nested ``(* … *)`` depth)
    """
    out: list[str] = []
    i = 0
    n = len(line)
    in_s = False
    depth: int = state.get("depth", 0)
    while i < n:
        if depth > 0:
            # inside a comment; look for ``(*`` or ``*)``.
            if line[i:i + 2] == "(*":
                depth += 1
                out.append("  ")
                i += 2
                continue
            if line[i:i + 2] == "*)":
                depth -= 1
                out.append("  ")
                i += 2
                continue
            out.append(" ")
            i += 1
            continue
        ch = line[i]
        if not in_s:
            if line[i:i + 2] == "(*":
                depth = 1
                out.append("  ")
                i += 2
                continue
            if ch == '"':
                in_s = True
                out.append(ch)
                i += 1
                continue
            out.append(ch)
            i += 1
            continue
        # inside string
        if ch == "\\" and i + 1 < n:
            out.append("  ")
            i += 2
            continue
        if ch == '"':
            in_s = False
            out.append(ch)
            i += 1
            continue
        out.append(" ")
        i += 1
    state["depth"] = depth
    return "".join(out)


def is_wolfram_file(path: Path) -> bool:
    if path.suffix in (".m", ".wl", ".wls"):
        return True
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            first = fh.readline()
    except OSError:
        return False
    if not first.startswith("#!"):
        return False
    return ("wolfram" in first) or ("MathKernel" in first)


def scan_file(path: Path) -> list[tuple[Path, int, int, str, str]]:
    findings: list[tuple[Path, int, int, str, str]] = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return findings
    state: dict = {"depth": 0}
    for idx, raw in enumerate(text.splitlines(), start=1):
        if RE_SUPPRESS.search(raw):
            strip_comments_and_strings(raw, state)
            continue
        scrub = strip_comments_and_strings(raw, state)
        seen_cols: set[int] = set()

        def emit(col: int) -> None:
            if col in seen_cols:
                return
            seen_cols.add(col)
            findings.append(
                (path, idx, col, "wolfram-eval", raw.strip())
            )

        for rx in (
            RE_TOEXPRESSION,
            RE_GET_FUNC,
            RE_NEEDS_FUNC,
            RE_RUNPROCESS,
            RE_RUN_FUNC,
            RE_GET_OP,
        ):
            for m in rx.finditer(scrub):
                emit(m.start(1) + 1)
    return findings


def iter_targets(roots: list[str]):
    for r in roots:
        p = Path(r)
        if p.is_dir():
            for sub in sorted(p.rglob("*")):
                if sub.is_file() and is_wolfram_file(sub):
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
