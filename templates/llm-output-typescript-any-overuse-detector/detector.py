#!/usr/bin/env python3
"""Detect overuse of `any` in TypeScript code fences within markdown.

Stdlib only. Code-fence aware. Reports each `: any` annotation, `as any`
cast, and `<...any...>` generic argument.
"""
from __future__ import annotations

import re
import sys
from typing import Iterator, Tuple

TS_LANGS = {"ts", "tsx", "typescript"}

FENCE_RE = re.compile(r"^(\s*)(```+|~~~+)\s*([^\s`~]*)")

# `: any` annotation. Boundary on the right keeps `anyone` from matching.
ANNOT_RE = re.compile(r":\s*any\b(?!\s*[A-Za-z_])")
# `as any` cast.
CAST_RE = re.compile(r"\bas\s+any\b")
# Generic argument containing `any` as a standalone token, e.g. Array<any>,
# Record<string, any>, Promise<any | null>.
GENERIC_RE = re.compile(r"<[^<>]*\bany\b[^<>]*>")
# Line / block comments to skip.
LINE_COMMENT_RE = re.compile(r"//.*$")
BLOCK_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)
STRING_RE = re.compile(r"(\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*'|`(?:\\.|[^`\\])*`)")


def iter_ts_fences(lines) -> Iterator[Tuple[int, int, str]]:
    """Yield (fence_index, start_line_1based, fence_body) for ts-ish fences."""
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
            # Closing fence: same marker char, length >= opener, only indent + marker.
            stripped = line.lstrip()
            if (
                stripped.startswith(fence_marker[0])
                and set(stripped.rstrip()) <= {fence_marker[0]}
                and len(stripped.rstrip()) >= len(fence_marker)
            ):
                if fence_lang in TS_LANGS:
                    yield fence_idx, fence_start, "\n".join(body)
                    fence_idx += 1
                in_fence = False
                fence_marker = ""
                fence_lang = ""
                body = []
            else:
                # Strip the fence indent if present.
                if fence_indent and line.startswith(fence_indent):
                    body.append(line[len(fence_indent):])
                else:
                    body.append(line)
    # Unterminated fence: still scan it.
    if in_fence and fence_lang in TS_LANGS:
        yield fence_idx, fence_start, "\n".join(body)


def scrub(line: str) -> str:
    """Remove strings and line comments so matches inside them don't count."""
    line = STRING_RE.sub('""', line)
    line = LINE_COMMENT_RE.sub("", line)
    return line


def lint_fence(body: str):
    """Yield (line_in_fence_1based, reason, snippet) for findings."""
    # Strip block comments globally before per-line scanning.
    body = BLOCK_COMMENT_RE.sub("", body)
    for j, raw in enumerate(body.splitlines(), start=1):
        clean = scrub(raw)
        for m in ANNOT_RE.finditer(clean):
            yield j, "type-annotation `any`", raw.strip()
            break
        for m in CAST_RE.finditer(clean):
            yield j, "cast `as any`", raw.strip()
            break
        for m in GENERIC_RE.finditer(clean):
            yield j, "generic arg `any`", raw.strip()
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
    for fence_idx, _start, body in iter_ts_fences(lines):
        for line_no, reason, snippet in lint_fence(body):
            print(f"fence#{fence_idx} line{line_no}: {reason} -> {snippet}")
            total += 1
    print(f"total findings: {total}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
