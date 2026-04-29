#!/usr/bin/env python3
"""Detect VBScript `Execute` / `ExecuteGlobal` / `Eval` runtime
code-evaluation sinks.

Classic VBScript (and VBA) ships three built-in constructs that take
a string and run it as VBScript:

    Execute       statement_string
    ExecuteGlobal statement_string
    result = Eval(expression_string)

Whenever the string is anything other than a manifest, audited
literal, the program is loading code chosen at runtime from data
that may be attacker-controllable: an InputBox, a registry value,
the body of an HTTP response, a database column, a filename argument
passed to a Windows Script Host script.

LLM-emitted VBScript reaches for `Execute` whenever the model wants
"a tiny config DSL" or "let the user supply a one-liner formula"
without knowing the safer patterns (parsing a fixed grammar,
dispatching on a small enum, or moving the dynamic surface to a
sandboxed host).

What this flags
---------------
* `Execute s`              — primary statement sink
* `Execute(s)`             — same, in call-syntax form
* `ExecuteGlobal s`        — global-scope variant
* `Eval(expr)` / `Eval e`  — expression-evaluation variant

We anchor the match on the keyword followed by whitespace or `(`,
so identifiers that merely contain `Execute` or `Eval`
(`ExecuteWorkbook`, `EvalScore`, `MyExecutor`) do not match.

Suppression
-----------
Append `' execute-ok` to the line to silence a vetted call.

Usage
-----
    python3 detect.py <file_or_dir> [<file_or_dir> ...]

Exit code 1 if any findings, 0 otherwise. python3 stdlib only.
Recurses into directories looking for `*.vbs`, `*.vbe`, `*.wsf`,
and `*.bas`.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


RE_SUPPRESS = re.compile(r"'\s*execute-ok\b", re.IGNORECASE)

# Keyword at start of a token, followed by whitespace OR `(`.
# VBScript keywords are case-insensitive.
RE_EVAL_CALL = re.compile(
    r"(?<![A-Za-z0-9_])(Execute\s*Global|ExecuteGlobal|Execute|Eval)(?=[\s(])",
    re.IGNORECASE,
)


def mask_vbs_comments_and_strings(text: str) -> str:
    """Replace comment and string-literal interiors with spaces while
    preserving column positions and newlines.

    VBScript lexical rules we cover:
      * `'` line comments (to end of line)
      * `Rem ...` line comments (whole-word `Rem`, case-insensitive,
        anywhere a statement may begin — we treat it as a comment
        whenever it appears as a standalone token at the start of a
        line, optionally preceded by whitespace, OR after a `:`
        statement separator)
      * `"..."` strings with VBScript's doubled-quote (`""`) escape
    """
    out = list(text)
    n = len(text)
    i = 0
    line_start = True

    def at_rem(pos: int) -> bool:
        if pos + 3 > n:
            return False
        if text[pos:pos + 3].lower() != "rem":
            return False
        # `Rem` must be a standalone token: next char is end, whitespace,
        # or a tab/newline; not an identifier char.
        nxt = text[pos + 3] if pos + 3 < n else "\n"
        if nxt.isalnum() or nxt == "_":
            return False
        return True

    while i < n:
        ch = text[i]
        if ch == "\n":
            line_start = True
            i += 1
            continue
        # Detect `Rem` only when at line-start (after optional whitespace)
        # or right after a `:` statement separator we just consumed.
        if line_start and ch in " \t":
            i += 1
            continue
        if line_start and at_rem(i):
            j = text.find("\n", i)
            if j == -1:
                j = n
            for k in range(i, j):
                out[k] = " "
            i = j
            line_start = True
            continue
        line_start = False
        # `'` line comment
        if ch == "'":
            j = text.find("\n", i)
            if j == -1:
                j = n
            for k in range(i, j):
                out[k] = " "
            i = j
            continue
        # `:` statement separator -> next non-space token may be Rem
        if ch == ":":
            i += 1
            # peek for Rem after spaces
            k = i
            while k < n and text[k] in " \t":
                k += 1
            if at_rem(k):
                j = text.find("\n", k)
                if j == -1:
                    j = n
                for m in range(k, j):
                    out[m] = " "
                i = j
                continue
            continue
        # "..." string with `""` escape
        if ch == '"':
            k = i + 1
            while k < n:
                c = text[k]
                if c == '"':
                    if k + 1 < n and text[k + 1] == '"':
                        k += 2
                        continue
                    break
                if c == "\n":
                    break
                k += 1
            end = k + 1 if k < n and text[k] == '"' else k
            for m in range(i + 1, max(i + 1, end - 1)):
                out[m] = " " if text[m] != "\n" else "\n"
            i = end
            continue
        i += 1
    return "".join(out)


def scan_file(path: Path) -> list[tuple[Path, int, int, str, str]]:
    findings: list[tuple[Path, int, int, str, str]] = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return findings
    masked = mask_vbs_comments_and_strings(text)
    raw_lines = text.splitlines()
    masked_lines = masked.splitlines()
    n = min(len(raw_lines), len(masked_lines))
    for idx in range(n):
        raw = raw_lines[idx]
        scrub = masked_lines[idx]
        if RE_SUPPRESS.search(raw):
            continue
        for m in RE_EVAL_CALL.finditer(scrub):
            kw = m.group(1).lower().replace(" ", "")
            kind = {
                "execute": "vbscript-execute",
                "executeglobal": "vbscript-execute-global",
                "eval": "vbscript-eval",
            }[kw]
            findings.append(
                (path, idx + 1, m.start() + 1, kind, raw.strip())
            )
    return findings


def is_vbs_file(path: Path) -> bool:
    return path.suffix.lower() in (".vbs", ".vbe", ".wsf", ".bas")


def iter_targets(roots: list[str]):
    for r in roots:
        p = Path(r)
        if p.is_dir():
            for sub in sorted(p.rglob("*")):
                if sub.is_file() and is_vbs_file(sub):
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
