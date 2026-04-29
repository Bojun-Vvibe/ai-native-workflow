#!/usr/bin/env python3
"""Detect dangerous dynamic-eval patterns in Wren source.

Wren's optional `meta` module exposes runtime compilation/evaluation:
  - Meta.eval(source)        ; compile + run a string in current module
  - Meta.compile(source)     ; compile a string into a callable Fn
  - Meta.compileExpression(s); compile a string into an expression Fn

Once you have a Fn from Meta.compile*, calling .call() on it is the
exec step. We flag both the compile and the eval directly, because the
compile is the precursor that turns attacker-controlled data into code.

Single-pass, stdlib-only, with comment + string-literal masking.

Wren lexical context handled by the masker:
  - // line comments
  - /* block comments */ (non-nesting; Wren block comments DO nest, but
    we conservatively treat them as non-nesting which means we may
    over-mask — never under-mask. Findings inside truly nested comments
    will be missed; findings outside are unaffected.)
  - "double-quoted" strings with \\ escapes
  - %(interpolation) inside strings is not specially handled; the whole
    string body up to the closing " is masked.

Usage:
    python3 detector.py <file-or-dir> [<file-or-dir> ...]

Exit code = number of findings (capped at 255).
"""
from __future__ import annotations
import os
import re
import sys
from typing import List, Tuple

_PATTERNS: List[Tuple[str, re.Pattern]] = [
    ("Meta.eval", re.compile(r"\bMeta\s*\.\s*eval\s*\(")),
    ("Meta.compileExpression", re.compile(r"\bMeta\s*\.\s*compileExpression\s*\(")),
    ("Meta.compile", re.compile(r"\bMeta\s*\.\s*compile\s*\(")),
]


def _mask(src: str) -> str:
    out = []
    i = 0
    n = len(src)
    while i < n:
        c = src[i]
        # // line comment
        if c == "/" and i + 1 < n and src[i + 1] == "/":
            j = src.find("\n", i)
            if j == -1:
                j = n
            out.append(" " * (j - i))
            i = j
            continue
        # /* block comment */ (treated as non-nesting)
        if c == "/" and i + 1 < n and src[i + 1] == "*":
            j = src.find("*/", i + 2)
            if j == -1:
                j = n
            else:
                j += 2
            # Preserve newlines inside the masked region so line numbers stay accurate.
            chunk = src[i:j]
            out.append("".join(ch if ch == "\n" else " " for ch in chunk))
            i = j
            continue
        # double-quoted string
        if c == '"':
            j = i + 1
            while j < n:
                if src[j] == "\\" and j + 1 < n:
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
            # Avoid double-reporting Meta.compile when Meta.compileExpression
            # also matched at the same offset.
            key = (m.start(), name)
            if key in seen:
                continue
            # If this is the substring "Meta.compile" of "Meta.compileExpression",
            # check the adjacent character.
            if name == "Meta.compile":
                end = m.end()  # points just after '('
                # find the '.' position again
                dot = masked.rfind(".", m.start(), end)
                if dot != -1:
                    after = masked[dot + 1 : end - 1]  # "compile"
                    # If the actual word in source was longer (compileExpression),
                    # it would have been matched by the more-specific regex; the
                    # `\s*\(` at the end forces us to match an opening paren right
                    # after `compile`, so this case is naturally excluded.
                    _ = after
            line_text = src_lines[ln - 1] if ln - 1 < len(src_lines) else ""
            findings.append((path, ln, name, line_text.strip()))
            seen.add(key)
    findings.sort(key=lambda t: (t[0], t[1]))
    return findings


def iter_files(roots):
    for root in roots:
        if os.path.isfile(root):
            yield root
            continue
        for dirpath, _, filenames in os.walk(root):
            for f in filenames:
                if f.endswith((".wren",)):
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
            print(f"{p}:{ln}: wren-dynamic-eval[{name}]: {txt}")
            total += 1
    print(f"--- {total} finding(s) ---", file=sys.stderr)
    return min(total, 255)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
