#!/usr/bin/env python3
"""Detect dangerous dynamic-eval patterns in Hy (Hy-on-Python lisp) source.

Patterns flagged:
  - (eval ...)             ; evaluates a quoted form / runtime data
  - (hy.eval ...)          ; explicit Hy eval
  - (hy.read ...)           ; parses a string into a form (precursor to eval)
  - (hy.read-many ...)      ; multi-form parse
  - (hy.eval-and-compile ...)
  - (exec ...)              ; Python interop exec
  - (compile ... "exec")    ; Python compile to exec mode

Single-pass, stdlib-only. Comments (`;` to EOL) and string literals (
including triple-quoted "..."/'''...''' and bracket strings #[[ ... ]])
are masked before pattern matching to reduce false positives.

Usage:
    python3 detector.py <file-or-dir> [<file-or-dir> ...]

Exit code: number of findings (capped at 255).
"""
from __future__ import annotations
import os
import re
import sys
from typing import List, Tuple

# Patterns: tuple of (name, regex). Match the opening of an s-expr call.
_PATTERNS: List[Tuple[str, re.Pattern]] = [
    ("hy.eval-and-compile", re.compile(r"\(\s*hy\.eval-and-compile\b")),
    ("hy.read-many", re.compile(r"\(\s*hy\.read-many\b")),
    ("hy.eval", re.compile(r"\(\s*hy\.eval(?![\w-])")),
    ("hy.read", re.compile(r"\(\s*hy\.read(?![\w-])")),
    ("eval", re.compile(r"\(\s*eval\b")),
    ("exec", re.compile(r"\(\s*exec\b")),
    ("compile-exec", re.compile(r"\(\s*compile\b[^)]*?\"exec\"")),
]


def _mask(src: str) -> str:
    """Replace contents of comments and string literals with spaces.

    Preserves line numbers / column offsets so regex hits map back to the
    original source location.
    """
    out = []
    i = 0
    n = len(src)
    while i < n:
        c = src[i]
        # Line comment ; ... \n
        if c == ";":
            j = src.find("\n", i)
            if j == -1:
                j = n
            out.append(" " * (j - i))
            i = j
            continue
        # Bracket string #[[ ... ]]  (Hy supports #[delim[ ... ]delim]; handle simple #[[ ]])
        if c == "#" and i + 2 < n and src[i + 1] == "[":
            # find a matching ]<same-delim>] — simplified: look for ']]'
            j = src.find("]]", i + 2)
            if j == -1:
                j = n
            else:
                j += 2
            out.append(" " * (j - i))
            i = j
            continue
        # Triple-quoted strings """ ... """ or ''' ... '''
        if (c == '"' or c == "'") and i + 2 < n and src[i + 1] == c and src[i + 2] == c:
            quote = c * 3
            j = src.find(quote, i + 3)
            if j == -1:
                j = n
            else:
                j += 3
            out.append(" " * (j - i))
            i = j
            continue
        # Single-line string " ... " or ' ... '
        if c == '"' or c == "'":
            quote = c
            j = i + 1
            while j < n:
                if src[j] == "\\" and j + 1 < n:
                    j += 2
                    continue
                if src[j] == quote:
                    j += 1
                    break
                if src[j] == "\n":
                    break
                j += 1
            out.append(" " * (j - i))
            i = j
            continue
        out.append(c)
        i += 1
    return "".join(out)


def scan(path: str, src: str) -> List[Tuple[str, int, str, str]]:
    masked = _mask(src)
    findings: List[Tuple[str, int, str, str]] = []
    # Pre-compute line starts for fast line-number lookup.
    line_starts = [0]
    for idx, ch in enumerate(src):
        if ch == "\n":
            line_starts.append(idx + 1)

    def lineno_for(offset: int) -> int:
        # binary search would be nicer; linear is fine for examples.
        lo, hi = 0, len(line_starts) - 1
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if line_starts[mid] <= offset:
                lo = mid
            else:
                hi = mid - 1
        return lo + 1

    for name, pat in _PATTERNS:
        for m in pat.finditer(masked):
            ln = lineno_for(m.start())
            line_text = src.splitlines()[ln - 1] if ln - 1 < len(src.splitlines()) else ""
            findings.append((path, ln, name, line_text.strip()))
    findings.sort(key=lambda t: (t[0], t[1]))
    return findings


def iter_files(roots):
    for root in roots:
        if os.path.isfile(root):
            yield root
            continue
        for dirpath, _, filenames in os.walk(root):
            for f in filenames:
                if f.endswith((".hy",)):
                    yield os.path.join(dirpath, f)


def main(argv: List[str]) -> int:
    if not argv:
        print("usage: detector.py <file-or-dir> [...]", file=sys.stderr)
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
            print(f"{p}:{ln}: hy-dynamic-eval[{name}]: {txt}")
            total += 1
    print(f"--- {total} finding(s) ---", file=sys.stderr)
    return min(total, 255)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
