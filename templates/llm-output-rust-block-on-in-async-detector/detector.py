#!/usr/bin/env python3
"""Detect synchronous block_on() calls nested inside async Rust code.

Stdlib only. Code-fence aware. Strips line/block comments and string
literals before matching.

Targets, when they appear inside the body of an `async fn` or `async {}`
or `async move {}` block within a ```rust / ```rs fence:

  - ``Handle::current().block_on(...)``
  - ``tokio::runtime::Handle::current().block_on(...)``
  - ``Runtime::new().unwrap().block_on(...)``
  - ``futures::executor::block_on(...)``
  - bare ``block_on(...)`` (heuristic; commonly the imported alias)

Calling ``block_on`` from an async context will panic on a multi-thread
tokio runtime and deadlock on a current-thread runtime. LLMs frequently
produce this pattern when they confuse "run a future" with "await a
future".
"""
from __future__ import annotations

import re
import sys
from typing import Iterator, Tuple, List

RUST_LANGS = {"rust", "rs"}

FENCE_RE = re.compile(r"^(\s*)(```+|~~~+)\s*([^\s`~]*)")

LINE_COMMENT_RE = re.compile(r"//.*$")
BLOCK_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)
STRING_RE = re.compile(r"\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*'")

# Patterns we consider "block_on" calls.
BLOCK_ON_PATTERNS = [
    (re.compile(r"\bfutures\s*::\s*executor\s*::\s*block_on\s*\("),
     "futures::executor::block_on inside async"),
    (re.compile(r"\btokio\s*::\s*runtime\s*::\s*Handle\s*::\s*current\s*\(\s*\)\s*\.\s*block_on\s*\("),
     "tokio Handle::current().block_on inside async"),
    (re.compile(r"\bHandle\s*::\s*current\s*\(\s*\)\s*\.\s*block_on\s*\("),
     "Handle::current().block_on inside async"),
    (re.compile(r"\bRuntime\s*::\s*new\s*\(\s*\)\s*[^;]*\.\s*block_on\s*\("),
     "Runtime::new()...block_on inside async"),
    # Heuristic: a bare `.block_on(` method call on something other than
    # the patterns above. Catches `rt.block_on(...)` etc.
    (re.compile(r"\.\s*block_on\s*\("),
     ".block_on() call inside async"),
    # Bare function-style `block_on(...)` (imported alias).
    (re.compile(r"(?<![\w:.])block_on\s*\("),
     "bare block_on() call inside async"),
]

ASYNC_FN_RE = re.compile(r"\basync\s+(?:unsafe\s+)?fn\b")
ASYNC_BLOCK_RE = re.compile(r"\basync\s+(?:move\s+)?\{")


def iter_rust_fences(lines) -> Iterator[Tuple[int, int, str]]:
    in_fence = False
    fence_marker = ""
    fence_indent = ""
    fence_lang = ""
    fence_start = 0
    body: List[str] = []
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


def scrub_line(line: str) -> str:
    line = STRING_RE.sub('""', line)
    line = LINE_COMMENT_RE.sub("", line)
    return line


def find_async_regions(body: str) -> List[Tuple[int, int]]:
    """Return [(start_line, end_line)] (1-indexed inclusive) for each
    async region (async fn body or async {} block), tracked by brace
    depth on the scrubbed text.
    """
    text = BLOCK_COMMENT_RE.sub(lambda m: " " * len(m.group(0)), body)
    lines = text.splitlines()
    scrubbed = [scrub_line(l) for l in lines]
    regions: List[Tuple[int, int]] = []

    # Pre-compute open-brace positions per line for both patterns.
    i = 0
    n = len(scrubbed)
    while i < n:
        line = scrubbed[i]
        match = ASYNC_FN_RE.search(line) or ASYNC_BLOCK_RE.search(line)
        if not match:
            i += 1
            continue
        # Find first `{` at-or-after the match column on this or
        # subsequent lines.
        col = match.end()
        depth = 0
        start_line = -1
        j = i
        c = col
        found_open = False
        while j < n and not found_open:
            row = scrubbed[j]
            while c < len(row):
                ch = row[c]
                if ch == "{":
                    depth = 1
                    start_line = j + 1
                    found_open = True
                    c += 1
                    break
                c += 1
            if not found_open:
                j += 1
                c = 0
        if not found_open:
            i += 1
            continue
        # Now walk until depth returns to 0.
        end_line = start_line
        while j < n and depth > 0:
            row = scrubbed[j]
            while c < len(row):
                ch = row[c]
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        end_line = j + 1
                        c += 1
                        break
                c += 1
            if depth > 0:
                j += 1
                c = 0
        regions.append((start_line, end_line))
        # Continue scan after this region's closing brace.
        i = j + 1 if depth == 0 else n
    return regions


def lint_fence(body: str):
    regions = find_async_regions(body)
    if not regions:
        return
    text = BLOCK_COMMENT_RE.sub(lambda m: " " * len(m.group(0)), body)
    for line_no, raw in enumerate(text.splitlines(), start=1):
        in_async = any(s <= line_no <= e for (s, e) in regions)
        if not in_async:
            continue
        clean = scrub_line(raw)
        for pat, reason in BLOCK_ON_PATTERNS:
            if pat.search(clean):
                yield line_no, reason, raw.strip()
                break  # one finding per line is enough


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
