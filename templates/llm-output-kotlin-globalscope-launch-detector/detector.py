#!/usr/bin/env python3
"""Detect GlobalScope.launch / GlobalScope.async usage in Kotlin code.

Stdlib only. Code-fence aware. Strips line/block comments and string
literals before matching.

Targets, inside ```kotlin / ```kt fences:

  - GlobalScope.launch { ... }
  - GlobalScope.async { ... }
  - GlobalScope.launch(...) { ... }
  - GlobalScope.async(...) { ... }
  - GlobalScope.future { ... }   (kotlinx-coroutines-jdk8)
  - GlobalScope.actor { ... }    (deprecated)

Bare `launch { ... }` and `async { ... }` are NOT flagged here — those
are CoroutineScope members and are typically fine. Only the
`GlobalScope.` receiver is the smell.
"""
from __future__ import annotations

import re
import sys
from typing import Iterator, Tuple, List

KOTLIN_LANGS = {"kotlin", "kt", "kts"}

FENCE_RE = re.compile(r"^(\s*)(```+|~~~+)\s*([^\s`~]*)")

LINE_COMMENT_RE = re.compile(r"//.*$")
BLOCK_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)
# Kotlin strings: ordinary "..." with escapes, and triple-quoted """...""".
TRIPLE_STRING_RE = re.compile(r'"""[\s\S]*?"""')
STRING_RE = re.compile(r'"(?:\\.|[^"\\])*"')
CHAR_RE = re.compile(r"'(?:\\.|[^'\\])'")

# Suppression marker on the same line. Mirrors other detectors in this
# repo: trailing comment containing "llm-detector: allow GlobalScope".
SUPPRESS_RE = re.compile(r"//\s*llm-detector:\s*allow\s+GlobalScope", re.IGNORECASE)

PATTERNS = [
    (re.compile(r"\bGlobalScope\s*\.\s*launch\b"),
     "GlobalScope.launch (use a structured CoroutineScope)"),
    (re.compile(r"\bGlobalScope\s*\.\s*async\b"),
     "GlobalScope.async (use a structured CoroutineScope)"),
    (re.compile(r"\bGlobalScope\s*\.\s*future\b"),
     "GlobalScope.future (jdk8) — bridge from a structured scope instead"),
    (re.compile(r"\bGlobalScope\s*\.\s*actor\b"),
     "GlobalScope.actor (deprecated and unstructured)"),
    (re.compile(r"\bGlobalScope\s*\.\s*produce\b"),
     "GlobalScope.produce (unstructured channel producer)"),
]


def iter_kotlin_fences(lines) -> Iterator[Tuple[int, int, str]]:
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
                if fence_lang in KOTLIN_LANGS:
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
    if in_fence and fence_lang in KOTLIN_LANGS:
        yield fence_idx, fence_start, "\n".join(body)


def scrub(line: str) -> str:
    line = STRING_RE.sub('""', line)
    line = CHAR_RE.sub("''", line)
    line = LINE_COMMENT_RE.sub("", line)
    return line


def lint_fence(body: str):
    body = BLOCK_COMMENT_RE.sub(lambda m: " " * len(m.group(0)), body)
    body = TRIPLE_STRING_RE.sub(lambda m: '""' + " " * (len(m.group(0)) - 2), body)
    for j, raw in enumerate(body.splitlines(), start=1):
        if SUPPRESS_RE.search(raw):
            continue
        clean = scrub(raw)
        for pat, reason in PATTERNS:
            if pat.search(clean):
                yield j, reason, raw.strip()
                break


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
    for fence_idx, _start, body in iter_kotlin_fences(lines):
        for line_no, reason, snippet in lint_fence(body):
            print(f"fence#{fence_idx} line{line_no}: {reason} -> {snippet}")
            total += 1
    print(f"total findings: {total}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
