#!/usr/bin/env python3
"""
llm-output-go-defer-in-loop-detector

Flags `defer` statements that appear inside `for` loops in Go source files.
LLMs frequently emit this pattern when translating "open / close" idioms,
producing code that holds resources until the enclosing function returns
instead of until the iteration ends.

Strategy: single-pass line scanner. We mask line and block comments and
string/rune literals, then track brace depth of `for` blocks and report any
`defer` token whose enclosing scope chain contains an unclosed `for`.

Stdlib only.
"""
from __future__ import annotations
import os
import sys
from typing import List, Tuple


def mask_line(src: str, in_block_comment: bool) -> Tuple[str, bool]:
    """Return (masked_line, in_block_comment_after).

    Replaces comments and string/rune literal contents with spaces so that
    keyword detection is not fooled.
    """
    out = []
    i = 0
    n = len(src)
    while i < n:
        c = src[i]
        nxt = src[i + 1] if i + 1 < n else ""
        if in_block_comment:
            if c == "*" and nxt == "/":
                out.append("  ")
                i += 2
                in_block_comment = False
            else:
                out.append(" ")
                i += 1
            continue
        if c == "/" and nxt == "/":
            out.append(" " * (n - i))
            break
        if c == "/" and nxt == "*":
            out.append("  ")
            i += 2
            in_block_comment = True
            continue
        if c == '"':
            out.append('"')
            i += 1
            while i < n:
                ch = src[i]
                if ch == "\\" and i + 1 < n:
                    out.append("  ")
                    i += 2
                    continue
                if ch == '"':
                    out.append('"')
                    i += 1
                    break
                out.append(" ")
                i += 1
            continue
        if c == "`":
            # raw string literal: contents until next backtick
            out.append("`")
            i += 1
            while i < n and src[i] != "`":
                out.append(" ")
                i += 1
            if i < n:
                out.append("`")
                i += 1
            continue
        if c == "'":
            out.append("'")
            i += 1
            while i < n:
                ch = src[i]
                if ch == "\\" and i + 1 < n:
                    out.append("  ")
                    i += 2
                    continue
                if ch == "'":
                    out.append("'")
                    i += 1
                    break
                out.append(" ")
                i += 1
            continue
        out.append(c)
        i += 1
    return "".join(out), in_block_comment


def is_word_boundary(s: str, idx: int, length: int) -> bool:
    if idx > 0:
        prev = s[idx - 1]
        if prev.isalnum() or prev == "_":
            return False
    end = idx + length
    if end < len(s):
        nxt = s[end]
        if nxt.isalnum() or nxt == "_":
            return False
    return True


def find_keyword(line: str, kw: str) -> List[int]:
    """Return list of column indices (0-based) where kw occurs as a whole word."""
    hits = []
    start = 0
    while True:
        j = line.find(kw, start)
        if j == -1:
            return hits
        if is_word_boundary(line, j, len(kw)):
            hits.append(j)
        start = j + 1


def scan_file(path: str) -> List[Tuple[int, str]]:
    """Return list of (lineno, message) hits."""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
    except OSError:
        return []
    lines = text.splitlines()
    hits: List[Tuple[int, str]] = []
    in_block_comment = False
    # Stack of scope kinds: each entry is one of {"for", "func", "block"}.
    # We push/pop on every `{` / `}` we see at the masked-line level.
    scope_stack: List[str] = []
    # Pending kind to apply to the NEXT `{` we encounter.
    pending: List[str] = []
    for ln, raw in enumerate(lines, 1):
        masked, in_block_comment = mask_line(raw, in_block_comment)

        # Find tokens of interest in column order:
        events: List[Tuple[int, str]] = []
        for col in find_keyword(masked, "for"):
            events.append((col, "kw_for"))
        for col in find_keyword(masked, "func"):
            events.append((col, "kw_func"))
        for col in find_keyword(masked, "defer"):
            events.append((col, "kw_defer"))
        for idx, ch in enumerate(masked):
            if ch == "{":
                events.append((idx, "lbrace"))
            elif ch == "}":
                events.append((idx, "rbrace"))
        events.sort(key=lambda x: x[0])

        for col, kind in events:
            if kind == "kw_for":
                pending.append("for")
            elif kind == "kw_func":
                pending.append("func")
            elif kind == "lbrace":
                if pending:
                    scope_stack.append(pending.pop(0))
                else:
                    scope_stack.append("block")
            elif kind == "rbrace":
                if scope_stack:
                    scope_stack.pop()
                # stray `}` ignored
            elif kind == "kw_defer":
                # Only flag if some enclosing scope is "for" AND inside a func.
                if "for" in scope_stack and "func" in scope_stack:
                    # Make sure the for is _inside_ the func (i.e. for appears after func in stack)
                    last_func = max(
                        i for i, s in enumerate(scope_stack) if s == "func"
                    )
                    if any(s == "for" for s in scope_stack[last_func:]):
                        hits.append(
                            (
                                ln,
                                "defer inside for-loop: resource released only at function return",
                            )
                        )
        # If a line ends without opening `{` for a pending kw_for/kw_func,
        # the keyword was used in another context (e.g. `for {`/`func()` on
        # the same line is already handled). If pending survives across many
        # lines (rare), it will eventually consume the next `{` we see.

    return hits


def iter_go_files(root: str):
    if os.path.isfile(root):
        if root.endswith(".go"):
            yield root
        return
    for dirpath, dirnames, filenames in os.walk(root):
        # skip vendor / .git
        dirnames[:] = [d for d in dirnames if d not in (".git", "vendor", "node_modules")]
        for fn in filenames:
            if fn.endswith(".go"):
                yield os.path.join(dirpath, fn)


def main(argv: List[str]) -> int:
    if len(argv) < 2:
        print("usage: detector.py <path> [<path> ...]", file=sys.stderr)
        return 2
    total = 0
    for root in argv[1:]:
        for path in iter_go_files(root):
            for ln, msg in scan_file(path):
                print(f"{path}:{ln}: {msg}")
                total += 1
    print(f"-- {total} hit(s)")
    return 0 if total == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
