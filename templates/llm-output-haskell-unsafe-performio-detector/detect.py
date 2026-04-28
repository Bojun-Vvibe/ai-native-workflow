#!/usr/bin/env python3
"""Detect Haskell `unsafePerformIO` (and friends) outside of test code.

`unsafePerformIO :: IO a -> a` lets you smuggle an `IO` action into a
pure context. It is occasionally legitimate (e.g. lazy global caches,
FFI wrappers), but in LLM-generated Haskell it almost always shows up
because the model wanted to "just print something" or "just read a
file" inside what was supposed to be a pure function — silently
breaking referential transparency.

Sibling escape hatches that are equally suspect:
- `unsafeDupablePerformIO`
- `unsafeInterleaveIO`
- `accursedUnutterablePerformIO` (bytestring-internal)

Usage:
    python3 detect.py <file_or_dir> [<file_or_dir> ...]

Exit code 1 if any findings, 0 otherwise. python3 stdlib only.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


UNSAFE_NAMES = (
    "unsafePerformIO",
    "unsafeDupablePerformIO",
    "unsafeInterleaveIO",
    "accursedUnutterablePerformIO",
)
RE_UNSAFE = re.compile(r"\b(" + "|".join(UNSAFE_NAMES) + r")\b")


def strip_comments_and_strings(line: str, in_block_comment: bool) -> tuple[str, bool]:
    """Blank out `-- ...` line comments, `{- ... -}` block comments,
    and `"..."` string literals while preserving column positions.
    Returns (scrubbed_line, still_in_block_comment)."""
    out: list[str] = []
    i = 0
    n = len(line)
    in_str = False
    block = in_block_comment
    while i < n:
        ch = line[i]
        nxt = line[i + 1] if i + 1 < n else ""
        if block:
            if ch == "-" and nxt == "}":
                out.append("  ")
                i += 2
                block = False
                continue
            out.append(" ")
            i += 1
            continue
        if in_str:
            if ch == "\\" and i + 1 < n:
                out.append("  ")
                i += 2
                continue
            if ch == '"':
                out.append(ch)
                in_str = False
                i += 1
                continue
            out.append(" ")
            i += 1
            continue
        # not in string, not in block comment
        if ch == "-" and nxt == "-":
            # line comment to EOL
            out.append(" " * (n - i))
            break
        if ch == "{" and nxt == "-":
            out.append("  ")
            i += 2
            block = True
            continue
        if ch == '"':
            out.append(ch)
            in_str = True
            i += 1
            continue
        out.append(ch)
        i += 1
    return "".join(out), block


def is_import_line(scrubbed: str) -> bool:
    s = scrubbed.lstrip()
    return s.startswith("import ")


def scan_file(path: Path) -> list[tuple[Path, int, int, str, str]]:
    findings: list[tuple[Path, int, int, str, str]] = []
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return findings
    raw_lines = raw.splitlines()
    in_block = False
    for idx, raw_line in enumerate(raw_lines):
        lineno = idx + 1
        scrub, in_block = strip_comments_and_strings(raw_line, in_block)
        # Skip import lines: `import System.IO.Unsafe (unsafePerformIO)`
        # mentions the symbol but is not a use site.
        if is_import_line(scrub):
            continue
        for m in RE_UNSAFE.finditer(scrub):
            name = m.group(1)
            findings.append(
                (path, lineno, m.start() + 1, f"unsafe-{name}", raw_line.strip())
            )
    return findings


def iter_targets(roots: list[str]):
    for r in roots:
        p = Path(r)
        if p.is_dir():
            for sub in sorted(list(p.rglob("*.hs")) + list(p.rglob("*.lhs"))):
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
