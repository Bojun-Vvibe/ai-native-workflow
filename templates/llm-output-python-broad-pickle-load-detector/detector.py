#!/usr/bin/env python3
"""
llm-output-python-broad-pickle-load-detector

Flags use of `pickle.load`, `pickle.loads`, `cPickle.load`, `cPickle.loads`,
and the bare aliases `load(...)` / `loads(...)` when imported as
`from pickle import load[s]`. Pickle deserialization of untrusted data
is arbitrary code execution; LLMs love to suggest pickle for "save / load
this object" without warning the caller.

Strategy: single-pass scanner. Mask comments and string literals, track
which names have been imported from `pickle` / `cPickle`, then flag the
unsafe call sites. Stdlib only.
"""
from __future__ import annotations
import os
import re
import sys
from typing import List, Set, Tuple


def mask_line(src: str) -> str:
    """Mask `#`-comments and Python string literals on a single line.

    Triple-quoted strings spanning lines are handled by the caller via
    a state flag — but we keep this function line-local for simplicity
    and rely on `mask_file` to set state.
    """
    out = []
    i = 0
    n = len(src)
    while i < n:
        c = src[i]
        if c == "#":
            out.append(" " * (n - i))
            break
        if c in ("'", '"'):
            quote = c
            # detect triple
            if src[i : i + 3] == quote * 3:
                # triple within a single physical line: find closing
                end = src.find(quote * 3, i + 3)
                if end == -1:
                    # unterminated on this line — caller handles
                    out.append(" " * (n - i))
                    return "".join(out)
                out.append(quote * 3)
                out.append(" " * (end - i - 3))
                out.append(quote * 3)
                i = end + 3
                continue
            out.append(quote)
            i += 1
            while i < n:
                ch = src[i]
                if ch == "\\" and i + 1 < n:
                    out.append("  ")
                    i += 2
                    continue
                if ch == quote:
                    out.append(quote)
                    i += 1
                    break
                out.append(" ")
                i += 1
            continue
        out.append(c)
        i += 1
    return "".join(out)


def mask_file(text: str) -> List[str]:
    """Mask comments + string literals across an entire file, handling
    triple-quoted strings that span multiple physical lines.
    """
    lines = text.splitlines()
    out_lines: List[str] = []
    in_triple = None  # None or the quote char
    for raw in lines:
        if in_triple is not None:
            quote = in_triple
            end = raw.find(quote * 3)
            if end == -1:
                out_lines.append(" " * len(raw))
                continue
            # close triple here
            head = " " * end + quote * 3
            tail = mask_line(raw[end + 3 :])
            out_lines.append(head + tail)
            in_triple = None
            continue
        # check whether this line opens an unterminated triple
        # do a quick scan: find first unmasked triple opener
        # Easier: try mask_line; if it returns short, we may have an open triple.
        # Detect open triple by walking
        i = 0
        n = len(raw)
        opener_idx = -1
        opener_q = None
        # walk respecting single-line strings and # comments to find a triple opener
        while i < n:
            c = raw[i]
            if c == "#":
                break
            if c in ("'", '"'):
                q = c
                if raw[i : i + 3] == q * 3:
                    # check whether it closes on same line
                    end = raw.find(q * 3, i + 3)
                    if end == -1:
                        opener_idx = i
                        opener_q = q
                        break
                    else:
                        i = end + 3
                        continue
                # single-line string
                i += 1
                while i < n:
                    ch = raw[i]
                    if ch == "\\" and i + 1 < n:
                        i += 2
                        continue
                    if ch == q:
                        i += 1
                        break
                    i += 1
                continue
            i += 1
        if opener_idx >= 0:
            head = mask_line(raw[:opener_idx])
            out_lines.append(head + opener_q * 3 + " " * (n - opener_idx - 3))
            in_triple = opener_q
        else:
            out_lines.append(mask_line(raw))
    return out_lines


IMPORT_PICKLE_RE = re.compile(
    r"^\s*import\s+(pickle|cPickle)(\s+as\s+(\w+))?\s*$"
)
FROM_PICKLE_RE = re.compile(
    r"^\s*from\s+(pickle|cPickle)\s+import\s+(.+)$"
)
NAME_AS_RE = re.compile(r"\b(\w+)\s*(?:as\s+(\w+))?")


def parse_imports(masked_lines: List[str]) -> Tuple[Set[str], Set[str]]:
    """Return (module_aliases, function_aliases).

    module_aliases: names that bind to the pickle module itself
        (e.g. `pickle`, or `p` from `import pickle as p`).
    function_aliases: names that bind to load/loads from pickle
        (e.g. `load`, `pload` from `from pickle import load as pload`).
    """
    mods: Set[str] = set()
    funcs: Set[str] = set()
    for line in masked_lines:
        m = IMPORT_PICKLE_RE.match(line)
        if m:
            alias = m.group(3) or m.group(1)
            mods.add(alias)
            continue
        m = FROM_PICKLE_RE.match(line)
        if m:
            tail = m.group(2).strip()
            # strip optional parens
            tail = tail.strip("()")
            for part in tail.split(","):
                part = part.strip()
                if not part:
                    continue
                pm = re.match(r"^(\w+)(?:\s+as\s+(\w+))?$", part)
                if not pm:
                    continue
                orig, alias = pm.group(1), pm.group(2)
                if orig in ("load", "loads", "Unpickler"):
                    funcs.add(alias or orig)
    return mods, funcs


def scan_file(path: str) -> List[Tuple[int, str]]:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
    except OSError:
        return []
    masked = mask_file(text)
    mods, funcs = parse_imports(masked)
    if not mods and not funcs:
        return []
    hits: List[Tuple[int, str]] = []
    # Build call-site regex set
    patterns: List[Tuple[re.Pattern, str]] = []
    for m in mods:
        patterns.append(
            (
                re.compile(r"\b" + re.escape(m) + r"\.(load|loads|Unpickler)\s*\("),
                f"{m}.<call>",
            )
        )
    for fn in funcs:
        patterns.append(
            (
                re.compile(r"(?<![\w.])" + re.escape(fn) + r"\s*\("),
                f"{fn}(...)",
            )
        )
    for ln, line in enumerate(masked, 1):
        for rx, label in patterns:
            for m in rx.finditer(line):
                hits.append(
                    (
                        ln,
                        f"unsafe pickle deserialization via {label}: "
                        f"untrusted bytes => arbitrary code execution",
                    )
                )
    return hits


def iter_py_files(root: str):
    if os.path.isfile(root):
        if root.endswith(".py"):
            yield root
        return
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [
            d
            for d in dirnames
            if d not in (".git", "__pycache__", ".venv", "venv", "node_modules")
        ]
        for fn in filenames:
            if fn.endswith(".py"):
                yield os.path.join(dirpath, fn)


def main(argv: List[str]) -> int:
    if len(argv) < 2:
        print("usage: detector.py <path> [<path> ...]", file=sys.stderr)
        return 2
    total = 0
    for root in argv[1:]:
        for path in iter_py_files(root):
            for ln, msg in scan_file(path):
                print(f"{path}:{ln}: {msg}")
                total += 1
    print(f"-- {total} hit(s)")
    return 0 if total == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
