#!/usr/bin/env python3
"""Detect overuse of .unwrap() / .expect() in Rust code fences.

Stdlib only. Code-fence aware. Strips line comments and string literals
so matches inside them do not count.
"""
from __future__ import annotations

import re
import sys
from typing import Iterator, Tuple

RUST_LANGS = {"rust", "rs"}

FENCE_RE = re.compile(r"^(\s*)(```+|~~~+)\s*([^\s`~]*)")

UNWRAP_RE = re.compile(r"\.unwrap\s*\(\s*\)")
EXPECT_RE = re.compile(r"\.expect\s*\(")
PANIC_OR_RE = re.compile(r"\.unwrap_or_else\s*\(\s*\|[^|]*\|\s*panic!\s*\(")

LINE_COMMENT_RE = re.compile(r"//.*$")
BLOCK_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)
# Rust string + char literals. Not a perfect parser but good enough to
# scrub `".unwrap()"` and `'.unwrap()'` from being matched.
STRING_RE = re.compile(r"\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*'")


def iter_rust_fences(lines) -> Iterator[Tuple[int, int, str]]:
    in_fence = False
    fence_marker = ""
    fence_indent = ""
    fence_lang = ""
    fence_start = 0
    body: list[str] = []
    fence_idx = 0
    for i, raw in enumerate(lines, start=1):
        line = raw.rstrip("\n")
        m = FENCE_RE.match(line)
        if not in_fence:
            if m:
                in_fence = True
                fence_indent = m.group(1)
                fence_marker = m.group(2)[0] * len(m.group(2))
                fence_lang = m.group(3).strip().lower()
                fence_start = i
                body = []
        else:
            stripped = line.lstrip()
            if (
                stripped.startswith(fence_marker[0])
                and set(stripped.rstrip()) <= {fence_marker[0]}
                and len(stripped.rstrip()) >= len(fence_marker)
            ):
                if fence_lang in RUST_LANGS:
                    yield fence_idx, fence_start, "\n".join(body)
                    fence_idx += 1
                in_fence = False
                fence_marker = ""
                fence_lang = ""
                body = []
            else:
                if fence_indent and line.startswith(fence_indent):
                    body.append(line[len(fence_indent):])
                else:
                    body.append(line)
    if in_fence and fence_lang in RUST_LANGS:
        yield fence_idx, fence_start, "\n".join(body)


def scrub(line: str) -> str:
    line = STRING_RE.sub('""', line)
    line = LINE_COMMENT_RE.sub("", line)
    return line


def lint_fence(body: str):
    body = BLOCK_COMMENT_RE.sub("", body)
    for j, raw in enumerate(body.splitlines(), start=1):
        clean = scrub(raw)
        seen = False
        if PANIC_OR_RE.search(clean):
            yield j, "unwrap_or_else(panic!) escape", raw.strip()
            seen = True
        if not seen and UNWRAP_RE.search(clean):
            yield j, ".unwrap() call", raw.strip()
            seen = True
        if not seen and EXPECT_RE.search(clean):
            yield j, ".expect(...) call", raw.strip()


def main(argv):
    if len(argv) != 2:
        print("usage: detector.py <markdown-file>", file=sys.stderr)
        return 2
    path = argv[1]
    try:
        with open(path, "r", encoding="utf-8") as fh:
            lines = fh.readlines()
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    total = 0
    for fence_idx, _start, body in iter_rust_fences(lines):
        for line_no, reason, snippet in lint_fence(body):
            print(f"fence#{fence_idx} line{line_no}: {reason} -> {snippet}")
            total += 1
    print(f"total findings: {total}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
