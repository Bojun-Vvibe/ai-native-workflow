#!/usr/bin/env python3
"""Detect PicoLisp `(eval ...)` / `(run ...)` / `(load ...)` /
`(str ... -> eval)` runtime code-load sinks.

PicoLisp exposes several functions that take Lisp data and execute
it as code:

    (eval expr)         # evaluate any expression at runtime
    (run prg)           # evaluate a body of expressions
    (load "file.l")     # read a file and evaluate every form in it
    (str "(+ 1 2)")     # parse a string into an expression -> often
                        # immediately fed into eval

Whenever the argument is anything other than a manifest, audited
literal, the program is loading code chosen at runtime from data
that may be attacker-controllable (config, network, REPL prompt,
HTTP body, query string).

LLM-generated PicoLisp code reaches for `eval` / `run` / `load`
whenever the model wants "a tiny config DSL" or "let the user
supply a hook" without knowing the safer patterns (a small
interpreter over a fixed grammar, or a restricted env).

What this flags
---------------
* `(eval ...)`   - primary sink
* `(run ...)`    - executes a list-of-forms as a program body
* `(load ...)`   - reads + evals a file; flagged unless argument is a
                   plain string literal (still reported, as policy says
                   "literal arg is still worth a look")
* `(str ...)` on the same line as `eval` - the `str -> eval` idiom

Suppression
-----------
Append `# eval-ok` to the line to silence a vetted call. PicoLisp
uses `#` for line comments, so the suppression marker is itself
a comment.

Usage
-----
    python3 detect.py <file_or_dir> [<file_or_dir> ...]

Exit code 1 if any findings, 0 otherwise. python3 stdlib only.
Recurses into directories looking for `*.l` and `*.lisp`.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


RE_SUPPRESS = re.compile(r"#\s*eval-ok\b")

# (eval ...), (run ...), (load ...) at form position. PicoLisp is
# case-sensitive; these built-ins are lowercase. We require the
# function name to be followed by whitespace or `)` so that names
# like `evaluate`, `runner`, `loaded?` are not matched.
RE_EVAL_CALL = re.compile(
    r"\(\s*(eval|run|load)(?=[\s\)])"
)

# `str` followed (possibly across the rest of the line) by `eval`
# is the parse-then-eval idiom. We just check both tokens appear on
# the same masked line, with str before eval.
RE_STR_TOKEN = re.compile(r"\(\s*str(?=[\s\)])")
RE_EVAL_TOKEN = re.compile(r"\(\s*eval(?=[\s\)])")


def mask_picolisp_comments_and_strings(text: str) -> str:
    """Replace comment and string-literal interiors with spaces while
    preserving column positions and newlines.

    PicoLisp lexical rules we cover:
      * `# line` comments (to end of line)
      * `#{ ... }#` block comments (rare but legal)
      * `"..."` strings with `^` escapes (PicoLisp uses `^` not `\\`,
        but we accept both `\\` and `^` as one-char escape leaders
        for safety)
    """
    out = list(text)
    n = len(text)
    i = 0
    while i < n:
        ch = text[i]
        # #{ ... }# block comment
        if ch == "#" and i + 1 < n and text[i + 1] == "{":
            j = text.find("}#", i + 2)
            if j == -1:
                j = n
            else:
                j += 2
            for k in range(i, j):
                out[k] = " " if text[k] != "\n" else "\n"
            i = j
            continue
        # # line comment
        if ch == "#":
            j = text.find("\n", i)
            if j == -1:
                j = n
            for k in range(i, j):
                out[k] = " " if text[k] != "\n" else "\n"
            i = j
            continue
        # "..." string with ^ or \ escapes
        if ch == '"':
            k = i + 1
            while k < n:
                c = text[k]
                if c in ("\\", "^") and k + 1 < n:
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
    masked = mask_picolisp_comments_and_strings(text)
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
                "eval": "picolisp-eval",
                "run": "picolisp-run",
                "load": "picolisp-load",
            }[sym]
            findings.append(
                (path, idx + 1, m.start() + 1, kind, raw.strip())
            )
        # str ... eval pipeline on same line, only if no plain (eval ...)
        # was already flagged on this line (avoid double reporting).
        str_m = RE_STR_TOKEN.search(scrub)
        ev_m = RE_EVAL_TOKEN.search(scrub)
        if str_m and ev_m and str_m.start() < ev_m.start():
            already = any(f[1] == idx + 1 and f[2] == ev_m.start() + 1
                          for f in findings)
            if not already:
                findings.append(
                    (path, idx + 1, str_m.start() + 1,
                     "picolisp-str-eval", raw.strip())
                )
    return findings


def is_picolisp_file(path: Path) -> bool:
    return path.suffix in (".l", ".lisp")


def iter_targets(roots: list[str]):
    for r in roots:
        p = Path(r)
        if p.is_dir():
            for sub in sorted(p.rglob("*")):
                if sub.is_file() and is_picolisp_file(sub):
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
