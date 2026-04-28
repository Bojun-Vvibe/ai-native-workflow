#!/usr/bin/env python3
"""llm-output-python-mixed-tabs-spaces-detector.

Pure-stdlib, code-fence-aware detector for Python code blocks that
mix tab and space characters in indentation — either within a
single line's leading whitespace, or across the lines of a single
block.

Why it matters
--------------
Python 3 makes mixing tabs and spaces a hard error
(``TabError: inconsistent use of tabs and spaces in indentation``)
in many — but not all — cases. The cases it does *not* catch are
the dangerous ones: a block that is uniformly tab-indented on some
lines and space-indented on others can parse and *run* but mean
something completely different than the author intended (the rule
is "tabs expand to the next multiple of 8 for tokenisation, but
the visual width may be 4 in the editor"). LLMs that emit Python
in markdown blocks frequently do this when they switch between
copying training data and synthesising new lines, because the
stop/start of generation does not preserve indentation
character-class. This detector flags both the per-line and
per-block forms at emit time.

Usage
-----
    python3 detect.py <markdown_file>

Reads the markdown file, finds fenced code blocks whose info-string
first token (case-insensitive) is one of {python, py, python3,
py3}, and reports each violation.

Output: one finding per line on stdout, of the form::

    block=<N> line=<L> kind=<k> [detail=...]

Trailing summary ``total_findings=<N> blocks_checked=<M>`` is
written to stderr. Exit code 0 if no findings, 1 if any, 2 on
bad usage.

What it flags
-------------
    mixed_in_line       A single line's leading whitespace contains
                        BOTH tab and space characters.
    block_mixed         The block as a whole has some indented
                        lines that are tab-led and others that are
                        space-led (each line is internally pure,
                        but the block disagrees with itself).
                        Reported once per block, on the first line
                        whose lead-character disagrees with the
                        baseline.

Out of scope (deliberately): indent *width* (2 vs 4 vs 8),
indent depth consistency across blocks, blank lines (their
"indentation" is meaningless), continuation lines inside
parentheses, and any AST-level analysis. This is a *first-line-
defense* sniff test, not a linter.
"""
from __future__ import annotations

import sys
from typing import List, Tuple


_PY_TAGS = {"python", "py", "python3", "py3"}


def extract_py_blocks(src: str) -> List[Tuple[int, int, str]]:
    """Return list of (block_idx, start_line_no, body) for each python block.

    start_line_no is the 1-indexed line of the first line *inside*
    the fence in the original file.
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
                    body_start = i + 2
                    i += 1
                    continue
            i += 1
            continue
        s = stripped.rstrip()
        if s and set(s) == {fence_char} and len(s) >= fence_len:
            if fence_tag in _PY_TAGS:
                block_idx += 1
                blocks.append((block_idx, body_start, "\n".join(body)))
            in_fence = False
            fence_tag = ""
            i += 1
            continue
        body.append(line)
        i += 1
    if in_fence and fence_tag in _PY_TAGS:
        block_idx += 1
        blocks.append((block_idx, body_start, "\n".join(body)))
    return blocks


def _leading_ws(line: str) -> str:
    j = 0
    while j < len(line) and line[j] in (" ", "\t"):
        j += 1
    return line[:j]


def detect_in_block(body: str) -> List[Tuple[int, str, str]]:
    """Return [(line_no, kind, detail)] findings within one python block."""
    findings: List[Tuple[int, str, str]] = []
    baseline_lead: str | None = None  # "tab" or "space"
    baseline_line: int | None = None
    block_mixed_reported = False
    for lineno, line in enumerate(body.split("\n"), start=1):
        if not line.strip():
            continue  # blank lines have no meaningful indent
        lead = _leading_ws(line)
        if not lead:
            continue
        has_tab = "\t" in lead
        has_space = " " in lead
        if has_tab and has_space:
            findings.append((lineno, "mixed_in_line",
                             f"lead_repr={lead!r}"))
            # Don't also evaluate block-baseline for this line: it's
            # already broken. But do continue scanning subsequent lines.
            continue
        kind = "tab" if has_tab else "space"
        if baseline_lead is None:
            baseline_lead = kind
            baseline_line = lineno
            continue
        if kind != baseline_lead and not block_mixed_reported:
            findings.append((lineno, "block_mixed",
                             f"baseline={baseline_lead}@line{baseline_line} "
                             f"this={kind}"))
            block_mixed_reported = True
    return findings


def main(argv: List[str]) -> int:
    if len(argv) != 2:
        print("usage: detect.py <markdown_file>", file=sys.stderr)
        return 2
    with open(argv[1], "r", encoding="utf-8") as fh:
        src = fh.read()
    blocks = extract_py_blocks(src)
    total = 0
    for block_idx, _start, body in blocks:
        for lineno, kind, detail in detect_in_block(body):
            total += 1
            tail = f" detail={detail}" if detail else ""
            print(f"block={block_idx} line={lineno} kind={kind}{tail}")
    print(f"total_findings={total} blocks_checked={len(blocks)}",
          file=sys.stderr)
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
