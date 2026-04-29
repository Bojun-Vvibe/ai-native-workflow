#!/usr/bin/env python3
"""Detect Fennel `(eval ...)` / `(eval-compiler ...)` /
`(fennel.eval ...)` / `(fennel.eval-string ...)` runtime
code-evaluation sinks.

Fennel is a Lisp that compiles to Lua. It exposes a small set of
forms / library calls that compile a Fennel form supplied as data
and run it inside the host Lua VM:

    (eval form)
    (eval-compiler ...)
    (fennel.eval src options)
    (fennel.eval-string src options)

Whenever the argument is anything other than a manifest, audited
literal, the program is loading code chosen at runtime from data
that may be attacker-controllable.

LLM-emitted Fennel code reaches for `eval` whenever the model wants
"a tiny config DSL" or "let the user supply a hook" without knowing
the safer patterns.

What this flags
---------------
* `(eval ...)`              — primary sink
* `(eval-compiler ...)`     — compiler-scope variant
* `(fennel.eval ...)`       — library entry point
* `(fennel.eval-string ...)`— older string variant

We anchor on `(`, optional whitespace, the symbol, then whitespace
or `)`. Identifiers that merely contain `eval` (`evaluate-score`,
`re-eval`, `evaluator`) do not match.

Suppression
-----------
Append `; eval-ok` to the line to silence a vetted call.

Usage
-----
    python3 detect.py <file_or_dir> [<file_or_dir> ...]

Exit code 1 if any findings, 0 otherwise. python3 stdlib only.
Recurses into directories looking for `*.fnl`.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


RE_SUPPRESS = re.compile(r";\s*eval-ok\b")

# Match (eval ...), (eval-compiler ...), (fennel.eval ...),
# (fennel.eval-string ...) at form position. Order longer alternatives
# first so the regex engine prefers them.
RE_EVAL_CALL = re.compile(
    r"\(\s*(fennel\.eval-string|fennel\.eval|eval-compiler|eval)(?=[\s)])"
)


def mask_fennel_comments_and_strings(text: str) -> str:
    """Replace comment and string-literal interiors with spaces while
    preserving column positions and newlines.

    Fennel lexical rules we cover:
      * `;` line comments (to end of line)
      * `"..."` strings with Lua-style `\\` escapes
    """
    out = list(text)
    n = len(text)
    i = 0
    while i < n:
        ch = text[i]
        # `;` line comment
        if ch == ";":
            j = text.find("\n", i)
            if j == -1:
                j = n
            for k in range(i, j):
                out[k] = " "
            i = j
            continue
        # "..." string with \\ escapes
        if ch == '"':
            k = i + 1
            while k < n:
                c = text[k]
                if c == "\\" and k + 1 < n:
                    k += 2
                    continue
                if c == '"':
                    break
                k += 1
            end = k + 1 if k < n else n
            for m in range(i + 1, max(i + 1, end - 1)):
                out[m] = text[m] if text[m] == "\n" else " "
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
    masked = mask_fennel_comments_and_strings(text)
    raw_lines = text.splitlines()
    masked_lines = masked.splitlines()
    n = min(len(raw_lines), len(masked_lines))
    for idx in range(n):
        raw = raw_lines[idx]
        scrub = masked_lines[idx]
        if RE_SUPPRESS.search(raw):
            continue
        for m in RE_EVAL_CALL.finditer(scrub):
            sym = m.group(1)
            kind = {
                "eval": "fennel-eval",
                "eval-compiler": "fennel-eval-compiler",
                "fennel.eval": "fennel-eval-string",
                "fennel.eval-string": "fennel-eval-string",
            }[sym]
            findings.append(
                (path, idx + 1, m.start() + 1, kind, raw.strip())
            )
    return findings


def is_fennel_file(path: Path) -> bool:
    return path.suffix == ".fnl"


def iter_targets(roots: list[str]):
    for r in roots:
        p = Path(r)
        if p.is_dir():
            for sub in sorted(p.rglob("*")):
                if sub.is_file() and is_fennel_file(sub):
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
