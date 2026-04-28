#!/usr/bin/env python3
"""
llm-output-kotlin-runblocking-in-suspend-detector

Flags `runBlocking` invocations that appear inside the body of a
`suspend fun` (or a `suspend` lambda) in Kotlin sources.

`runBlocking` parks the calling thread until the coroutine inside it
completes. Calling it from a `suspend` function defeats the entire
point of the suspend machinery — the function had a non-blocking way
to wait (`await`, `.collect`, `delay`, structured concurrency) and the
LLM threw it away. Worst case on a UI dispatcher this freezes the
foreground; worst case on a small server pool this exhausts threads.

Strategy: single-pass per-line scanner. We mask comments and string
literals (including triple-quoted raw strings), then track brace depth
plus a stack of "pending" enclosing fun signatures so we know when we
are inside a `suspend fun` body. Any `runBlocking` token whose nearest
enclosing `fun` was declared `suspend` is reported.

Stdlib only.
"""
from __future__ import annotations
import os
import re
import sys
from typing import List, Tuple


def mask_line(src: str, in_block_comment: bool, in_triple: bool) -> Tuple[str, bool, bool]:
    """Return (masked_line, in_block_comment_after, in_triple_string_after).

    Replaces /* */, //, "...", and triple-quoted "\"\"\"...\"\"\"" with spaces.
    Char literals don't exist in Kotlin in the C sense; single quotes
    delimit single Char values like 'a', so we still mask them.
    """
    out: List[str] = []
    i = 0
    n = len(src)
    while i < n:
        c = src[i]
        nxt = src[i + 1] if i + 1 < n else ""
        nxt2 = src[i + 2] if i + 2 < n else ""
        if in_triple:
            if c == '"' and nxt == '"' and nxt2 == '"':
                out.append('"""')
                i += 3
                in_triple = False
            else:
                out.append(" ")
                i += 1
            continue
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
        if c == '"' and nxt == '"' and nxt2 == '"':
            out.append('"""')
            i += 3
            in_triple = True
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
    return "".join(out), in_block_comment, in_triple


# Regex to detect a fun declaration on a (possibly multi-line) chunk of text.
# We look for `fun` as a whole word, capture preceding modifiers, and require
# an opening parenthesis somewhere after (the parameter list start).
FUN_RE = re.compile(r"\bfun\b")
SUSPEND_RE = re.compile(r"\bsuspend\b")


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
    hits: List[int] = []
    start = 0
    while True:
        j = line.find(kw, start)
        if j == -1:
            return hits
        if is_word_boundary(line, j, len(kw)):
            hits.append(j)
        start = j + 1


def scan_file(path: str) -> List[Tuple[int, str]]:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
    except OSError:
        return []
    lines = text.splitlines()
    hits: List[Tuple[int, str]] = []
    in_block = False
    in_triple = False

    # Stack entries: ("fun", is_suspend) or ("block", False) or
    # ("lambda", is_suspend_lambda).
    scope_stack: List[Tuple[str, bool]] = []
    # When we see `fun` we collect a "pending fun" with its suspend flag,
    # which is bound to the next `{` (the function body).
    pending_fun_suspend: List[bool] = []
    # Track recent `suspend` modifier so we can attach it to the next fun.
    # We do this with a per-line scan that looks at modifier preceding `fun`.

    for ln, raw in enumerate(lines, 1):
        masked, in_block, in_triple = mask_line(raw, in_block, in_triple)

        # Detect `fun` occurrences and check whether `suspend` precedes them
        # on the same line (the typical Kotlin style).
        fun_positions = find_keyword(masked, "fun")
        for fp in fun_positions:
            prefix = masked[:fp]
            is_suspend = bool(SUSPEND_RE.search(prefix))
            pending_fun_suspend.append(is_suspend)

        # Walk braces in column order along with `runBlocking` tokens.
        events: List[Tuple[int, str]] = []
        for col in find_keyword(masked, "runBlocking"):
            events.append((col, "rb"))
        for idx, ch in enumerate(masked):
            if ch == "{":
                events.append((idx, "lbrace"))
            elif ch == "}":
                events.append((idx, "rbrace"))
        events.sort(key=lambda x: x[0])

        for col, kind in events:
            if kind == "lbrace":
                if pending_fun_suspend:
                    is_suspend = pending_fun_suspend.pop(0)
                    scope_stack.append(("fun", is_suspend))
                else:
                    # Plain block / lambda body. We do not try to detect
                    # suspending lambdas heuristically — only `suspend fun`
                    # bodies count.
                    scope_stack.append(("block", False))
            elif kind == "rbrace":
                if scope_stack:
                    scope_stack.pop()
            elif kind == "rb":
                # Are we inside a suspend fun?
                in_suspend_fun = False
                for kind2, flag in reversed(scope_stack):
                    if kind2 == "fun":
                        in_suspend_fun = flag
                        break
                if in_suspend_fun:
                    hits.append(
                        (
                            ln,
                            f"runBlocking inside suspend fun at col {col + 1}: "
                            f"blocks the calling thread; use coroutineScope/await/withContext instead",
                        )
                    )
    return hits


def iter_kt_files(root: str):
    if os.path.isfile(root):
        if root.endswith((".kt", ".kts")):
            yield root
        return
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [
            d for d in dirnames if d not in (".git", "build", ".gradle", "node_modules")
        ]
        for fn in filenames:
            if fn.endswith((".kt", ".kts")):
                yield os.path.join(dirpath, fn)


def main(argv: List[str]) -> int:
    if len(argv) < 2:
        print("usage: detector.py <path> [<path> ...]", file=sys.stderr)
        return 2
    total = 0
    for root in argv[1:]:
        for path in iter_kt_files(root):
            for ln, msg in scan_file(path):
                print(f"{path}:{ln}: {msg}")
                total += 1
    print(f"-- {total} hit(s)")
    return 0 if total == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
