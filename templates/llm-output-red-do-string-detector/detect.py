#!/usr/bin/env python3
"""Detect dangerous dynamic-eval patterns in Red source.

Red (https://www.red-lang.org/) inherits Rebol's homoiconic philosophy:
strings can be turned back into runnable code at any time. The classic
sinks LLM-generated Red code reaches for are:

  do      <string|word>      ; evaluate a string/block as Red source
  do/expand <...>            ; expand macros then evaluate
  do/next <...>              ; evaluate one expression at a time
  load    <string>           ; parse a string into a value/block (often
                             ; followed by `do`)
  load/all <string>          ; same, but accepts a header

`load` alone is "just parse", but the LLM idiom `do load some-string`
or `do load/all some-string` is a textbook RCE sink when `some-string`
is attacker-controllable. We flag both `do` and `load` so reviewers
can audit either side of the chain.

Single-pass, stdlib-only, with comment + string-literal masking.

Red lexical context handled by the masker:
  - `;` line comments to end-of-line
  - `"..."` strings with `^` (caret) escapes
  - `{...}` curly-brace strings — these DO nest in Red, and we honour
    that. `^{` and `^}` inside braced strings escape the brace and do
    not change nesting depth.

Note: we deliberately do NOT try to detect/strip the `comment` form
(e.g. `comment {ignored block}`) because it is a regular function call,
not a lexical construct, and parsing it correctly would require a real
Red lexer. This means a `do <string>` literally inside a `comment {...}`
would be flagged as a false positive — acceptable for a lint.

Usage:
    python3 detect.py <file-or-dir> [<file-or-dir> ...]

Exit code = number of findings (capped at 255).
"""
from __future__ import annotations
import os
import re
import sys
from typing import List, Tuple


# `do` and `load` are case-insensitive in Red, but the canonical lower-case
# form is overwhelmingly what LLMs emit. We match case-insensitively to be
# safe. The trailing lookahead requires whitespace or a `/refinement` to
# avoid matching `do-something` (a word with a dash).
_PATTERNS: List[Tuple[str, re.Pattern]] = [
    # do/expand, do/next, do/args, plain do
    ("do", re.compile(r"(?i)(?<![A-Za-z0-9_!?\-])do(?:/[A-Za-z]+)*(?=\s|\")")),
    # load, load/all, load/header, load/part
    ("load", re.compile(r"(?i)(?<![A-Za-z0-9_!?\-])load(?:/[A-Za-z]+)*(?=\s|\")")),
]


def _mask(src: str) -> str:
    """Replace comment and string contents with spaces (preserving newlines)."""
    out = []
    i = 0
    n = len(src)
    while i < n:
        c = src[i]
        # ; line comment
        if c == ";":
            j = src.find("\n", i)
            if j == -1:
                j = n
            out.append(" " * (j - i))
            i = j
            continue
        # "..." string with ^ escape
        if c == '"':
            j = i + 1
            while j < n:
                if src[j] == "^" and j + 1 < n:
                    j += 2
                    continue
                if src[j] == '"':
                    j += 1
                    break
                j += 1
            chunk = src[i:j]
            out.append("".join(ch if ch == "\n" else " " for ch in chunk))
            i = j
            continue
        # {...} braced string with nesting; ^{ and ^} escape
        if c == "{":
            j = i + 1
            depth = 1
            while j < n and depth > 0:
                if src[j] == "^" and j + 1 < n:
                    j += 2
                    continue
                if src[j] == "{":
                    depth += 1
                elif src[j] == "}":
                    depth -= 1
                    if depth == 0:
                        j += 1
                        break
                j += 1
            chunk = src[i:j]
            out.append("".join(ch if ch == "\n" else " " for ch in chunk))
            i = j
            continue
        out.append(c)
        i += 1
    return "".join(out)


def scan(path: str, src: str) -> List[Tuple[str, int, str, str]]:
    masked = _mask(src)
    findings: List[Tuple[str, int, str, str]] = []
    line_starts = [0]
    for idx, ch in enumerate(src):
        if ch == "\n":
            line_starts.append(idx + 1)

    def lineno_for(offset: int) -> int:
        lo, hi = 0, len(line_starts) - 1
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if line_starts[mid] <= offset:
                lo = mid
            else:
                hi = mid - 1
        return lo + 1

    src_lines = src.splitlines()
    seen = set()
    for name, pat in _PATTERNS:
        for m in pat.finditer(masked):
            ln = lineno_for(m.start())
            key = (m.start(), name)
            if key in seen:
                continue
            line_text = src_lines[ln - 1] if ln - 1 < len(src_lines) else ""
            findings.append((path, ln, name, line_text.strip()))
            seen.add(key)
    findings.sort(key=lambda t: (t[0], t[1], t[2]))
    return findings


def iter_files(roots):
    for root in roots:
        if os.path.isfile(root):
            yield root
            continue
        for dirpath, _, filenames in os.walk(root):
            for f in filenames:
                if f.endswith((".red", ".reds")):
                    yield os.path.join(dirpath, f)


def main(argv: List[str]) -> int:
    if not argv:
        print("usage: detect.py <file-or-dir> [...]", file=sys.stderr)
        return 2
    total = 0
    for path in iter_files(argv):
        try:
            with open(path, "r", encoding="utf-8") as fh:
                src = fh.read()
        except (OSError, UnicodeDecodeError) as e:
            print(f"{path}: skip ({e})", file=sys.stderr)
            continue
        for p, ln, name, txt in scan(path, src):
            print(f"{p}:{ln}: red-dynamic-eval[{name}]: {txt}")
            total += 1
    print(f"--- {total} finding(s) ---", file=sys.stderr)
    return min(total, 255)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
