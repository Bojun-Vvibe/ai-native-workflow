#!/usr/bin/env python3
"""
llm-output-lua-pcall-result-discarded-detector

Flags `pcall(...)` and `xpcall(...)` calls in Lua sources whose return
value (the `(ok, err)` tuple) is thrown away by being used purely as a
statement.

`pcall` exists *exclusively* to convert raised errors into a boolean +
error-value pair so the caller can decide what to do. Using
`pcall(fn, ...)` as a bare statement collapses this back into a silent
swallow:

    pcall(do_request, url)        -- network error: silently lost
    pcall(json.decode, payload)   -- parse failure: caller has no idea

The error is captured by `pcall`, then immediately discarded because
nothing reads the boolean it returned. This is strictly worse than
calling `do_request(url)` directly — at least there the error would
crash and be visible.

LLMs produce this constantly when asked to "make this safer" or
"add error handling". The model knows `pcall` is the answer to
"how do I not crash on errors in Lua", but doesn't realise the
two-value return must actually be inspected.

Strategy: single-pass per-line scanner. Mask comments (`--` line and
`--[[ ]]` block, including long-bracket variants `--[==[ ]==]`) and
string literals (single, double, and long-bracket `[[ ]]` /
`[==[ ]==]`). Then look for `pcall` / `xpcall` calls whose enclosing
statement does not bind their result to a local, an assignment target,
a return, an `if`/`while`/`elseif`/`until`/`assert(`/`and`/`or`
context, or a call argument.

Stdlib only.
"""
from __future__ import annotations
import os
import re
import sys
from typing import List, Tuple


# -- masking ----------------------------------------------------------------

LONG_OPEN_RE = re.compile(r"\[(=*)\[")


def _scan_long_close(src: str, start: int, eq_count: int) -> int:
    """Return index just past the matching `]==]`, or len(src) if unterminated."""
    needle = "]" + ("=" * eq_count) + "]"
    j = src.find(needle, start)
    if j == -1:
        return len(src)
    return j + len(needle)


def mask_source(text: str) -> str:
    """Replace comments and string literals with spaces, preserving
    line structure (newlines kept) so line numbers stay accurate."""
    out: List[str] = []
    i = 0
    n = len(text)
    while i < n:
        c = text[i]
        nxt = text[i + 1] if i + 1 < n else ""
        # Long bracket comment: --[==[ ... ]==]
        if c == "-" and nxt == "-":
            # Check if this is a long-bracket comment
            after = text[i + 2 : i + 2 + 64]
            m = LONG_OPEN_RE.match(after)
            if m:
                eq_count = len(m.group(1))
                body_start = i + 2 + m.end()
                close_end = _scan_long_close(text, body_start, eq_count)
                # Replace whole region with spaces (keep newlines).
                for k in range(i, close_end):
                    out.append("\n" if text[k] == "\n" else " ")
                i = close_end
                continue
            # Line comment: -- ... \n
            j = text.find("\n", i)
            if j == -1:
                j = n
            for k in range(i, j):
                out.append(" ")
            i = j
            continue
        # Long bracket string: [==[ ... ]==]
        if c == "[":
            m = LONG_OPEN_RE.match(text, i)
            if m:
                eq_count = len(m.group(1))
                body_start = m.end()
                close_end = _scan_long_close(text, body_start, eq_count)
                for k in range(i, close_end):
                    out.append("\n" if text[k] == "\n" else " ")
                i = close_end
                continue
        # Short string: "..." or '...'
        if c == '"' or c == "'":
            quote = c
            out.append(quote)
            i += 1
            while i < n:
                ch = text[i]
                if ch == "\\" and i + 1 < n:
                    out.append("  " if text[i + 1] != "\n" else " \n")
                    i += 2
                    continue
                if ch == quote:
                    out.append(quote)
                    i += 1
                    break
                if ch == "\n":
                    # Unterminated string; bail to newline.
                    out.append("\n")
                    i += 1
                    break
                out.append(" ")
                i += 1
            continue
        out.append(c)
        i += 1
    return "".join(out)


# -- statement-context check -----------------------------------------------

PCALL_RE = re.compile(r"\b(x?pcall)\s*\(")


def _matching_paren(s: str, open_idx: int) -> int:
    """Return index of matching `)` for `(` at open_idx; len(s) if unmatched."""
    depth = 0
    i = open_idx
    n = len(s)
    while i < n:
        c = s[i]
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return n


# Tokens that, if they appear as the immediate left-context of a pcall
# *call expression* on the same logical line, mean the result is being
# consumed. We treat presence of `=`, `local`, `return`, `if`, `elseif`,
# `while`, `until`, `and`, `or`, `not`, `,`, `(` (call argument), `assert(`
# as "consumed".
CONSUMING_LEFT_RE = re.compile(
    r"(=|\blocal\b|\breturn\b|\bif\b|\belseif\b|\bwhile\b|\buntil\b|"
    r"\band\b|\bor\b|\bnot\b|\bassert\s*\(|,|\()\s*$"
)


def find_statements_in_line(line: str) -> List[Tuple[int, int]]:
    """Split a line into (start, end) ranges by `;` separators (Lua
    statement separators) plus the whole line as the default. We don't
    deeply parse; for our purposes, statements separated by `;` on one
    line are independent."""
    spans: List[Tuple[int, int]] = []
    last = 0
    depth = 0
    for i, c in enumerate(line):
        if c == "(" or c == "{" or c == "[":
            depth += 1
        elif c == ")" or c == "}" or c == "]":
            if depth > 0:
                depth -= 1
        elif c == ";" and depth == 0:
            spans.append((last, i))
            last = i + 1
    spans.append((last, len(line)))
    return spans


def scan_file(path: str) -> List[Tuple[int, str]]:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
    except OSError:
        return []
    masked = mask_source(text)
    hits: List[Tuple[int, str]] = []
    for ln_idx, raw_line in enumerate(masked.splitlines(), 1):
        for span_start, span_end in find_statements_in_line(raw_line):
            stmt = raw_line[span_start:span_end]
            for m in PCALL_RE.finditer(stmt):
                kw_start = m.start()
                paren_open = m.end() - 1  # the '(' captured by regex
                # Find matching ')'
                rel_close = _matching_paren(stmt, paren_open)
                # Examine left context within this statement only.
                left = stmt[:kw_start]
                if CONSUMING_LEFT_RE.search(left):
                    continue
                # Examine right context: anything after the closing paren
                # other than whitespace / `;` means the result is used
                # in a chain (e.g., method call) — treat as consumed.
                tail = stmt[rel_close + 1 :].strip()
                if tail and not tail.startswith(("--",)):
                    # Could be a method call like pcall(f)() — consumed.
                    continue
                col = span_start + kw_start + 1
                kw = m.group(1)
                hits.append(
                    (
                        ln_idx,
                        f"{kw} result discarded at col {col}: "
                        f"the (ok, err) tuple is thrown away — error is "
                        f"silently swallowed; bind it: `local ok, err = "
                        f"{kw}(...)` and check `ok`",
                    )
                )
    return hits


def iter_lua_files(root: str):
    if os.path.isfile(root):
        if root.endswith((".lua", ".rockspec")):
            yield root
        return
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [
            d for d in dirnames
            if d not in (".git", "node_modules", ".luarocks", "build")
        ]
        for fn in filenames:
            if fn.endswith(".lua"):
                yield os.path.join(dirpath, fn)


def main(argv: List[str]) -> int:
    if len(argv) < 2:
        print("usage: detector.py <path> [<path> ...]", file=sys.stderr)
        return 2
    total = 0
    for root in argv[1:]:
        for path in iter_lua_files(root):
            for ln, msg in scan_file(path):
                print(f"{path}:{ln}: {msg}")
                total += 1
    print(f"-- {total} hit(s)")
    return 0 if total == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
