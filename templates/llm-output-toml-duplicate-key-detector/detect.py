#!/usr/bin/env python3
"""llm-output-toml-duplicate-key-detector.

Pure-stdlib, code-fence-aware detector for *duplicate keys at the same
table scope* in TOML blocks emitted by an LLM inside a markdown
document.

TOML 1.0.0 says duplicate keys MUST raise an error. Real-world
parsers do — but the LLM that emitted the doc has no parser in the
loop, so it happily produces:

    [package]
    name = "foo"
    name = "bar"          # second one wins? or error? depends.

or, more insidiously:

    port = 8080
    port = 8081

The bug only surfaces when the doc is finally fed to a parser, often
in production. This detector flags it at emit time.

Usage
-----
    python3 detect.py <markdown_file>

Reads the markdown file, finds fenced code blocks whose info-string
first token (case-insensitive) is one of {toml, conf, config, ini}
(ini is included because LLMs often mislabel TOML as ini), and runs
the duplicate-key check on each.

Output: one finding per line on stdout, of the form:
    block=<N> line=<L> kind=duplicate_key key=<k> first_line=<L0>

A trailing summary `total_findings=<N> blocks_checked=<M>` is printed
to stderr. Exit code 0 if no findings, 1 if any.

What it flags
-------------
    duplicate_key   Same bare/quoted key appears twice inside the
                    same active table or inline-table scope.

Scope rules
-----------
    [a.b]           opens a new active table. Keys defined under it
                    do NOT collide with keys under [a.c] or [a].
    [[arr]]         opens a new array-of-tables element. Each
                    [[arr]] gets its own scope.
    inline = { a=1, b=2 }   inline tables are their own scope.

Out of scope (deliberately, to keep the detector simple and
deterministic): multi-line strings, dotted-key creation of implicit
tables, mixing dotted-key + table-header for the same path. A grammar
checker is somebody else's template.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import List, Tuple


@dataclass(frozen=True)
class Finding:
    block_idx: int
    line_no: int     # 1-indexed within the fenced block
    kind: str
    key: str
    first_line_no: int


_TOML_TAGS = {"toml", "conf", "config", "ini"}


def extract_toml_blocks(src: str) -> List[Tuple[int, int, str]]:
    """Return list of (block_idx, start_line_no, body) for each TOML block.

    start_line_no is the 1-indexed line of the first line *inside* the
    fence (i.e. the line after the opening ```).
    """
    blocks: List[Tuple[int, int, str]] = []
    lines = src.splitlines()
    i = 0
    in_fence = False
    fence_char = ""
    fence_len = 0
    fence_tag = ""
    body: List[str] = []
    body_start = 0
    block_idx = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.lstrip()
        if not in_fence:
            if stripped.startswith("```") or stripped.startswith("~~~"):
                ch = stripped[0]
                run = 0
                while run < len(stripped) and stripped[run] == ch:
                    run += 1
                if run >= 3:
                    info = stripped[run:].strip()
                    tag = info.split()[0].lower() if info else ""
                    in_fence = True
                    fence_char = ch
                    fence_len = run
                    fence_tag = tag
                    body = []
                    body_start = i + 2  # next line is 1-indexed body line 1; file line is i+2
                    i += 1
                    continue
            i += 1
            continue
        # in_fence
        if stripped.startswith(fence_char * fence_len) and set(stripped.rstrip()) <= {fence_char}:
            # closing fence
            if fence_tag in _TOML_TAGS:
                block_idx += 1
                blocks.append((block_idx, body_start, "\n".join(body)))
            in_fence = False
            fence_tag = ""
            i += 1
            continue
        body.append(line)
        i += 1
    # unterminated fence: still emit if it was a TOML tag
    if in_fence and fence_tag in _TOML_TAGS:
        block_idx += 1
        blocks.append((block_idx, body_start, "\n".join(body)))
    return blocks


def _strip_comment(line: str) -> str:
    """Strip a '#' comment, respecting basic-string and literal-string quoting."""
    out = []
    i = 0
    in_basic = False
    in_literal = False
    while i < len(line):
        c = line[i]
        if in_basic:
            out.append(c)
            if c == "\\" and i + 1 < len(line):
                out.append(line[i + 1])
                i += 2
                continue
            if c == '"':
                in_basic = False
            i += 1
            continue
        if in_literal:
            out.append(c)
            if c == "'":
                in_literal = False
            i += 1
            continue
        if c == "#":
            break
        if c == '"':
            in_basic = True
        elif c == "'":
            in_literal = True
        out.append(c)
        i += 1
    return "".join(out)


def _parse_key(s: str) -> str:
    """Parse a TOML key (possibly quoted, possibly dotted). Return canonical form."""
    s = s.strip()
    parts = []
    i = 0
    while i < len(s):
        if s[i] == '"':
            j = i + 1
            buf = []
            while j < len(s) and s[j] != '"':
                if s[j] == "\\" and j + 1 < len(s):
                    buf.append(s[j:j + 2])
                    j += 2
                    continue
                buf.append(s[j])
                j += 1
            parts.append("".join(buf))
            i = j + 1
        elif s[i] == "'":
            j = i + 1
            buf = []
            while j < len(s) and s[j] != "'":
                buf.append(s[j])
                j += 1
            parts.append("".join(buf))
            i = j + 1
        else:
            j = i
            while j < len(s) and s[j] not in ".= \t":
                j += 1
            if j > i:
                parts.append(s[i:j])
            i = j
            if i < len(s) and s[i] == ".":
                i += 1
            else:
                break
    return ".".join(parts)


def detect_in_block(body: str) -> List[Tuple[int, str, int]]:
    """Return list of (line_no, key, first_line_no) findings within one TOML block."""
    findings: List[Tuple[int, str, int]] = []
    # scope_key -> {dotted_key: first_line_no}
    seen: dict = {"": {}}
    current_scope = ""
    for lineno, raw in enumerate(body.split("\n"), start=1):
        line = _strip_comment(raw).strip()
        if not line:
            continue
        if line.startswith("[["):
            # array of tables — each [[..]] is a fresh scope, name uniqued by line
            end = line.find("]]")
            if end < 0:
                continue
            tbl = line[2:end].strip()
            current_scope = f"[[{tbl}#{lineno}]]"
            seen.setdefault(current_scope, {})
            continue
        if line.startswith("["):
            end = line.find("]")
            if end < 0:
                continue
            tbl = line[1:end].strip()
            current_scope = tbl
            seen.setdefault(current_scope, {})
            continue
        # key = value line
        eq = line.find("=")
        if eq < 0:
            continue
        key_part = line[:eq]
        try:
            key = _parse_key(key_part)
        except Exception:
            continue
        if not key:
            continue
        scope_map = seen[current_scope]
        if key in scope_map:
            findings.append((lineno, key, scope_map[key]))
        else:
            scope_map[key] = lineno
    return findings


def main(argv: List[str]) -> int:
    if len(argv) != 2:
        print("usage: detect.py <markdown_file>", file=sys.stderr)
        return 2
    with open(argv[1], "r", encoding="utf-8") as fh:
        src = fh.read()
    blocks = extract_toml_blocks(src)
    total = 0
    for block_idx, _start, body in blocks:
        for lineno, key, first in detect_in_block(body):
            total += 1
            print(f"block={block_idx} line={lineno} kind=duplicate_key "
                  f"key={key} first_line={first}")
    print(f"total_findings={total} blocks_checked={len(blocks)}", file=sys.stderr)
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
