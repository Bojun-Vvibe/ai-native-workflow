#!/usr/bin/env python3
"""Detect Janet `(eval ...)` / `(eval-string ...)` / `(dofile ...)` /
`(parse ...)` -into-eval string-evaluation sinks.

Janet (the Lisp dialect) exposes a small set of functions that compile
and run a Janet form supplied as data:

    (eval form)
    (eval-string "(+ 1 2)")
    (dofile "user-script.janet")
    (eval (parse user-input))

Whenever the argument is anything other than a manifest, audited
literal, the program is loading code chosen at runtime from data
that may be attacker-controllable (config, network, REPL prompt,
HTTP body).

LLM-generated Janet code reaches for `eval` whenever the model wants
"a tiny config DSL" or "let the user supply a hook" without knowing
the safer patterns (a small interpreter over a fixed grammar, or a
PEG / spork sandbox).

What this flags
---------------
* `(eval ...)`          — primary sink
* `(eval-string ...)`   — string variant
* `(dofile ...)`        — loads and runs another Janet source file
* `(parse ...)` followed by `eval` — flagged when on the same line
  as `eval`, since the typical pattern is `(eval (parse s))`

We flag whenever the call appears at form position. Literal arguments
are still flagged: even a literal-argument `eval` is worth a manual
review because it usually means the model didn't know the static
form was available.

Suppression
-----------
Append `# eval-ok` to the line to silence a vetted call.

Usage
-----
    python3 detect.py <file_or_dir> [<file_or_dir> ...]

Exit code 1 if any findings, 0 otherwise. python3 stdlib only.
Recurses into directories looking for `*.janet` and `*.jdn`.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


RE_SUPPRESS = re.compile(r"#\s*eval-ok\b")

# (eval ...), (eval-string ...), (dofile ...) at form position.
# Janet identifiers are case-sensitive and may include hyphens.
RE_EVAL_CALL = re.compile(
    r"\(\s*(eval-string|eval|dofile)(?=[\s\)])"
)


def mask_janet_comments_and_strings(text: str) -> str:
    """Replace comment and string-literal interiors with spaces while
    preserving column positions and newlines.

    Janet lexical rules we cover:
      * `# line` comments (to end of line)
      * `"..."` strings with `\\` escapes
      * `` `long string` ``  long strings (one or more backticks
        as the delimiter, matching count closes the string)
    """
    out = list(text)
    n = len(text)
    i = 0
    while i < n:
        ch = text[i]
        # # line comment
        if ch == "#":
            j = text.find("\n", i)
            if j == -1:
                j = n
            for k in range(i, j):
                out[k] = " " if text[k] != "\n" else "\n"
            i = j
            continue
        # backtick long string: `....`, ``....``, etc. (matching count)
        if ch == "`":
            count = 0
            k = i
            while k < n and text[k] == "`":
                count += 1
                k += 1
            opener_end = k
            # find the matching run of `count` backticks
            close = -1
            scan = opener_end
            while scan < n:
                if text[scan] == "`":
                    run = 0
                    s2 = scan
                    while s2 < n and text[s2] == "`":
                        run += 1
                        s2 += 1
                    if run >= count:
                        # match: closing run is `count` backticks at scan..scan+count
                        close = scan
                        break
                    scan = s2
                else:
                    scan += 1
            if close == -1:
                end = n
                content_end = n
            else:
                content_end = close
                end = close + count
            for m in range(opener_end, content_end):
                out[m] = text[m] if text[m] == "\n" else " "
            i = end
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
    masked = mask_janet_comments_and_strings(text)
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
                "eval": "janet-eval",
                "eval-string": "janet-eval-string",
                "dofile": "janet-dofile",
            }[sym]
            findings.append(
                (path, idx + 1, m.start() + 1, kind, raw.strip())
            )
    return findings


def is_janet_file(path: Path) -> bool:
    return path.suffix in (".janet", ".jdn")


def iter_targets(roots: list[str]):
    for r in roots:
        p = Path(r)
        if p.is_dir():
            for sub in sorted(p.rglob("*")):
                if sub.is_file() and is_janet_file(sub):
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
