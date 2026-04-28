#!/usr/bin/env python3
"""Detect Go sync.Mutex / sync.RWMutex / sync.WaitGroup passed or
embedded by value.

Stdlib only. Code-fence aware (handles ```go and ```golang fenced
blocks in markdown). Also runs directly on .go files (entire file
treated as one fence body when no fences are detected).

Heuristics flagged:
  - Struct field embedding a sync mutex/waitgroup as a non-pointer
    value (e.g. `mu sync.Mutex`). This is fine for the *first* such
    embedding when the struct is consumed by pointer receivers, but
    LLM output frequently then writes value-receiver methods or
    passes the struct by value. We flag both the field declaration
    AND any value-receiver method on a struct that contains such a
    field, because copying ANY struct with an embedded mutex is
    almost always a bug.
  - Function or method parameters of type `sync.Mutex`, `sync.RWMutex`,
    `sync.WaitGroup`, `sync.Once`, `sync.Cond`, or `sync.Map` passed
    by value (no leading `*`).
  - Method receivers on structs that contain a sync mutex field where
    the receiver is a value (no `*`).

Prints findings as `path:line:col: msg`.
False-positive notes:
  - Pointer fields (`mu *sync.Mutex`) are intentionally not flagged.
  - We do not flag `sync.Locker` interface values (they are pointers
    in practice).
  - Comments and strings are scrubbed before matching.
"""
from __future__ import annotations

import re
import sys
from typing import Iterator, List, Tuple

GO_LANGS = {"go", "golang"}

FENCE_RE = re.compile(r"^(\s*)(```+|~~~+)\s*([^\s`~]*)")

LINE_COMMENT_RE = re.compile(r"//.*$")
BLOCK_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)
STRING_RE = re.compile(r'"(?:\\.|[^"\\])*"|`[^`]*`')

SYNC_TYPES = ("Mutex", "RWMutex", "WaitGroup", "Once", "Cond", "Map")
SYNC_TYPE_ALT = "|".join(SYNC_TYPES)

# Field declaration: `name sync.Mutex` (not `*sync.Mutex`).
FIELD_RE = re.compile(
    rf"^\s*(\w+)\s+sync\.({SYNC_TYPE_ALT})\b"
)
# Embedded (anonymous) field: `sync.Mutex` on its own line in struct.
EMBED_RE = re.compile(
    rf"^\s*sync\.({SYNC_TYPE_ALT})\s*$"
)
# Function/method parameter sync.Mutex by value. Matches inside
# parens after a function signature: `(mu sync.Mutex, ...)` or
# `func f(mu sync.Mutex)`.
PARAM_RE = re.compile(
    rf"\(\s*[^)]*?\b\w+\s+sync\.({SYNC_TYPE_ALT})\b"
)
# Value receiver: `func (s Foo) Bar(...)` (no `*`). We capture the
# receiver type for cross-check against struct fields seen earlier.
VALUE_RECV_RE = re.compile(
    r"^\s*func\s*\(\s*\w+\s+(\w+)\s*\)\s+\w+"
)
# Struct opening: `type Foo struct {`.
STRUCT_OPEN_RE = re.compile(r"^\s*type\s+(\w+)\s+struct\s*\{")
# Naive close.
CLOSE_BRACE_RE = re.compile(r"^\s*\}")


def iter_go_blocks(lines: List[str]) -> Iterator[Tuple[int, List[str]]]:
    """Yield (start_line_1based, body_lines) for each go fence.

    If no fence is detected at all, yield the whole file as one block
    starting at line 1, so the detector is useful on raw `.go` files.
    """
    in_fence = False
    fence_marker = ""
    fence_indent = ""
    fence_lang = ""
    fence_start = 0
    body: List[str] = []
    saw_any_fence = False

    for i, raw in enumerate(lines, start=1):
        line = raw.rstrip("\n")
        m = FENCE_RE.match(line)
        if not in_fence:
            if m:
                saw_any_fence = True
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
                if fence_lang in GO_LANGS:
                    yield fence_start, body
                in_fence = False
                fence_marker = ""
                fence_lang = ""
                body = []
            else:
                if fence_indent and line.startswith(fence_indent):
                    body.append(line[len(fence_indent):])
                else:
                    body.append(line)
    if in_fence and fence_lang in GO_LANGS:
        yield fence_start, body
    if not saw_any_fence:
        yield 1, [l.rstrip("\n") for l in lines]


def scrub(line: str) -> str:
    line = STRING_RE.sub('""', line)
    line = LINE_COMMENT_RE.sub("", line)
    return line


def lint_block(start_line: int, body: List[str], path: str) -> int:
    body_text = "\n".join(body)
    body_text = BLOCK_COMMENT_RE.sub("", body_text)
    rebuilt = body_text.splitlines()

    structs_with_mutex: set = set()
    in_struct: str = ""
    findings = 0

    for j, raw in enumerate(rebuilt):
        clean = scrub(raw)
        # Track struct context.
        ms = STRUCT_OPEN_RE.match(clean)
        if ms:
            in_struct = ms.group(1)
            continue
        if in_struct and CLOSE_BRACE_RE.match(clean):
            in_struct = ""
            continue

        if in_struct:
            mf = FIELD_RE.match(clean)
            me = EMBED_RE.match(clean)
            if mf and "*" not in clean.split("sync.")[0]:
                line_no = start_line + j
                col = clean.find("sync.") + 1
                print(f"{path}:{line_no}:{col}: sync.{mf.group(2)} field by value in struct {in_struct}")
                structs_with_mutex.add(in_struct)
                findings += 1
            elif me:
                line_no = start_line + j
                col = clean.find("sync.") + 1
                print(f"{path}:{line_no}:{col}: anonymous sync.{me.group(1)} embedded by value in struct {in_struct}")
                structs_with_mutex.add(in_struct)
                findings += 1
            continue

        # Param-by-value.
        for pm in PARAM_RE.finditer(clean):
            line_no = start_line + j
            col = pm.start() + 1
            print(f"{path}:{line_no}:{col}: sync.{pm.group(1)} parameter passed by value")
            findings += 1

        # Value receiver on struct that contains a mutex.
        vr = VALUE_RECV_RE.match(clean)
        if vr and vr.group(1) in structs_with_mutex:
            line_no = start_line + j
            col = clean.find(vr.group(1)) + 1
            print(f"{path}:{line_no}:{col}: value receiver on {vr.group(1)} which embeds a sync mutex (copies the lock)")
            findings += 1

    return findings


def main(argv):
    if len(argv) != 2:
        print("usage: detector.py <file>", file=sys.stderr)
        return 2
    path = argv[1]
    try:
        with open(path, "r", encoding="utf-8") as fh:
            lines = fh.readlines()
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    total = 0
    for start, body in iter_go_blocks(lines):
        total += lint_block(start, body, path)
    print(f"total findings: {total}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
