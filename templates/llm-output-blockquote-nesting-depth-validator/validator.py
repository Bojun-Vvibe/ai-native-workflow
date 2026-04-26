#!/usr/bin/env python3
"""
llm-output-blockquote-nesting-depth-validator
=============================================

Stdlib-only validator for CommonMark-style blockquote nesting in
LLM-emitted Markdown. The model is asked to quote a source, then
quote a quote inside it, and the resulting `>` / `> >` / `> > >`
prefixes drift in ways that look fine to a reader but break every
downstream Markdown renderer.

Six finding classes (one per line, deterministic order):

- ``depth_jump``                — depth increased by more than 1
                                  between adjacent blockquote
                                  lines (e.g. ``>`` immediately
                                  followed by ``> > >``). Renders
                                  inconsistently across CommonMark
                                  and GFM.
- ``mixed_marker_spacing``      — within ONE blockquote line the
                                  ``>`` markers use inconsistent
                                  trailing spaces, e.g. ``>>``
                                  next to ``> >`` next to ``>  >``
                                  on neighboring lines at the
                                  same depth.
- ``trailing_space_after_gt``   — a blockquote line ends with a
                                  bare ``>`` and trailing
                                  whitespace, no content. Some
                                  renderers eat the next paragraph
                                  into the quote.
- ``empty_quote_line``          — a ``>`` line with nothing after
                                  it, surrounded by content lines
                                  at a deeper depth. Often a
                                  hallucinated separator the model
                                  inserted to "look like" a real
                                  reply structure.
- ``unindented_continuation``   — a non-blockquote line directly
                                  follows a blockquote line of
                                  depth >= 2 without a blank line.
                                  CommonMark would merge it into
                                  the deepest quote; the model
                                  almost certainly meant to exit.
- ``max_depth_exceeded``        — depth > MAX_DEPTH (default 4).
                                  Beyond this, every renderer
                                  disagrees. If the model is
                                  emitting depth 5+, it is almost
                                  certainly wrong.

Input: a Markdown file path on argv[1].
Output: JSONL on stdout, one finding per line.
Exit code: 0 always.
"""

from __future__ import annotations

import json
import re
import sys
from typing import Any


MAX_DEPTH = 4
# matches the leading run of '>' markers, capturing how they were
# written (so we can detect inconsistent inter-marker spacing)
GT_RUN = re.compile(r"^([ \t]*(?:>[ \t]*)+)(.*)$")


def _parse_line(line: str) -> tuple[int, str, str] | None:
    """Return (depth, marker_run, content) or None if not a blockquote line."""
    m = GT_RUN.match(line)
    if not m:
        return None
    run = m.group(1)
    content = m.group(2)
    depth = run.count(">")
    if depth == 0:
        return None
    return depth, run, content


def _normalize_marker(run: str) -> str:
    """Collapse marker spacing to a canonical token like '>_>_' for compare."""
    # keep gt/space pattern, drop leading whitespace
    stripped = run.lstrip(" \t")
    return re.sub(r"[ \t]", "_", stripped)


def _emit(findings: list[dict[str, Any]], **kw: Any) -> None:
    findings.append(kw)


def validate(text: str) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    lines = text.splitlines()
    parsed: list[tuple[int, str, str] | None] = [_parse_line(l) for l in lines]

    # 1. depth_jump and 6. max_depth_exceeded
    prev_depth = 0
    for i, p in enumerate(parsed):
        if p is None:
            prev_depth = 0
            continue
        depth, _, _ = p
        if depth > MAX_DEPTH:
            _emit(
                findings,
                line=i + 1,
                kind="max_depth_exceeded",
                detail=f"depth={depth} max={MAX_DEPTH}",
            )
        if depth > prev_depth + 1:
            _emit(
                findings,
                line=i + 1,
                kind="depth_jump",
                detail=f"prev_depth={prev_depth} depth={depth}",
            )
        prev_depth = depth

    # 2. mixed_marker_spacing — group adjacent same-depth lines, check
    #    whether their normalized marker tokens disagree.
    i = 0
    while i < len(parsed):
        if parsed[i] is None:
            i += 1
            continue
        depth_i, _, _ = parsed[i]
        j = i
        while (
            j < len(parsed)
            and parsed[j] is not None
            and parsed[j][0] == depth_i
        ):
            j += 1
        group = [(k + 1, parsed[k][1]) for k in range(i, j)]
        norms = {_normalize_marker(r) for _, r in group}
        if len(norms) > 1:
            # report on the first line of the group
            _emit(
                findings,
                line=group[0][0],
                kind="mixed_marker_spacing",
                detail=f"depth={depth_i} variants={sorted(norms)}",
            )
        i = j

    # 3. trailing_space_after_gt and 4. empty_quote_line
    for i, (raw, p) in enumerate(zip(lines, parsed)):
        if p is None:
            continue
        depth, run, content = p
        # bare '> ' style line means content is empty after the marker run
        if content == "":
            # tail = whitespace AFTER the last '>' character in the raw line
            last_gt = raw.rfind(">")
            tail = raw[last_gt + 1:]
            if tail != "":
                _emit(
                    findings,
                    line=i + 1,
                    kind="trailing_space_after_gt",
                    detail=f"depth={depth} trailing_chars={len(tail)}",
                )
            else:
                _emit(
                    findings,
                    line=i + 1,
                    kind="empty_quote_line",
                    detail=f"depth={depth}",
                )

    # 5. unindented_continuation
    for i in range(len(parsed) - 1):
        cur = parsed[i]
        nxt = parsed[i + 1]
        if cur is None:
            continue
        if cur[0] < 2:
            continue
        if nxt is not None:
            continue
        # next line must be non-blank, non-blockquote, no leading blank
        if lines[i + 1].strip() == "":
            continue
        _emit(
            findings,
            line=i + 2,
            kind="unindented_continuation",
            detail=f"prev_depth={cur[0]}",
        )

    findings.sort(key=lambda f: (f["line"], f["kind"]))
    return findings


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: validator.py FILE.md", file=sys.stderr)
        return 2
    with open(argv[1], "r", encoding="utf-8") as fh:
        text = fh.read()
    for f in validate(text):
        print(json.dumps(f, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
