#!/usr/bin/env python3
"""
llm-output-c-strcpy-unbounded-detector

Flags calls to unbounded C string functions in `.c` / `.h` source:

    strcpy(dst, src)
    strcat(dst, src)
    sprintf(dst, fmt, ...)
    gets(buf)

These functions write without a size argument and are the classic
buffer-overflow primitives. Bounded equivalents — `strncpy`, `strlcpy`,
`strncat`, `strlcat`, `snprintf`, `fgets` — exist for every one of them
and should be preferred.

LLMs reach for the unbounded forms because they dominate older training
data (K&R-era textbooks, beginner tutorials). The bounded forms have
lower frequency, so under uncertainty the model defaults to the unsafe
shape.

Strategy: single-pass per-line scanner. Comments (`//`, `/* */`) and
string/char literals are masked to spaces so that the keywords inside
them don't trigger. After masking, we look for each banned name as a
whole identifier immediately followed (skipping whitespace) by `(`.

Stdlib only.
"""
from __future__ import annotations
import os
import sys
from typing import List, Tuple


BANNED = ("strcpy", "strcat", "sprintf", "gets", "vsprintf")


def mask_line(src: str, in_block_comment: bool) -> Tuple[str, bool]:
    """Return (masked_line, in_block_comment_after).

    Replaces comments and string/char literal contents with spaces.
    """
    out: List[str] = []
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


def is_word_boundary_left(s: str, idx: int) -> bool:
    if idx == 0:
        return True
    prev = s[idx - 1]
    return not (prev.isalnum() or prev == "_")


def find_call_sites(line: str, name: str) -> List[int]:
    """Return columns where `name` appears as a whole identifier
    immediately followed (after optional whitespace) by '('."""
    hits: List[int] = []
    start = 0
    L = len(name)
    n = len(line)
    while True:
        j = line.find(name, start)
        if j == -1:
            return hits
        start = j + 1
        if not is_word_boundary_left(line, j):
            continue
        end = j + L
        # whitespace then '('
        k = end
        while k < n and line[k] in " \t":
            k += 1
        if k < n and line[k] == "(":
            hits.append(j)


def scan_file(path: str) -> List[Tuple[int, str]]:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
    except OSError:
        return []
    hits: List[Tuple[int, str]] = []
    in_block_comment = False
    for ln, raw in enumerate(text.splitlines(), 1):
        masked, in_block_comment = mask_line(raw, in_block_comment)
        for name in BANNED:
            for col in find_call_sites(masked, name):
                hits.append(
                    (
                        ln,
                        f"unbounded `{name}(` call at col {col + 1}: "
                        f"prefer bounded equivalent (snprintf/strncpy/strlcpy/fgets)",
                    )
                )
    return hits


def iter_c_files(root: str):
    if os.path.isfile(root):
        if root.endswith((".c", ".h")):
            yield root
        return
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [
            d for d in dirnames if d not in (".git", "build", "node_modules", "third_party")
        ]
        for fn in filenames:
            if fn.endswith((".c", ".h")):
                yield os.path.join(dirpath, fn)


def main(argv: List[str]) -> int:
    if len(argv) < 2:
        print("usage: detector.py <path> [<path> ...]", file=sys.stderr)
        return 2
    total = 0
    for root in argv[1:]:
        for path in iter_c_files(root):
            for ln, msg in scan_file(path):
                print(f"{path}:{ln}: {msg}")
                total += 1
    print(f"-- {total} hit(s)")
    return 0 if total == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
