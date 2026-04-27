#!/usr/bin/env python3
"""Detect markdown lists that mix loose (blank-line-separated) and tight items.

A list is "loose" if any of its items are separated by one or more blank lines,
"tight" otherwise. CommonMark renders loose lists with <p> tags inside <li>,
which produces visually different vertical spacing. LLMs frequently emit lists
where some items have a blank line before them and others don't, producing
inconsistent rendering.

This script reports each list group whose items have inconsistent blank-line
separation: i.e. at least one pair of adjacent items has a blank line between
them and at least one pair does not.

Reads stdin, writes findings to stdout, exits 1 on findings, 0 on clean input.
"""

from __future__ import annotations

import re
import sys

LIST_ITEM_RE = re.compile(r"^(\s*)([-*+]|\d+[.)])\s+")
FENCE_RE = re.compile(r"^\s*(```|~~~)")


def main() -> int:
    lines = sys.stdin.read().splitlines()

    in_fence = False
    # A "list group" = consecutive list items at the same indent level,
    # possibly separated by blank lines (CommonMark allows up to one blank
    # line of separation while still belonging to the same list).
    # We track per-indent groups.
    # group: list of dicts {line_no (1-based), indent, blanks_before}
    groups: list[list[dict]] = []
    current_group: list[dict] = []
    blanks_since_last_item = 0
    last_indent: int | None = None

    def close_group() -> None:
        nonlocal current_group
        if current_group:
            groups.append(current_group)
            current_group = []

    for idx, line in enumerate(lines, start=1):
        if FENCE_RE.match(line):
            in_fence = not in_fence
            close_group()
            blanks_since_last_item = 0
            last_indent = None
            continue
        if in_fence:
            continue

        if line.strip() == "":
            blanks_since_last_item += 1
            # Two or more blanks definitively ends a list.
            if blanks_since_last_item >= 2:
                close_group()
                last_indent = None
            continue

        m = LIST_ITEM_RE.match(line)
        if m:
            indent = len(m.group(1))
            if last_indent is not None and indent != last_indent:
                close_group()
            current_group.append(
                {
                    "line": idx,
                    "indent": indent,
                    "blanks_before": blanks_since_last_item if current_group else 0,
                }
            )
            last_indent = indent
            blanks_since_last_item = 0
        else:
            # Non-list, non-blank line. If indented more than current list,
            # treat as continuation. Otherwise close the group.
            if last_indent is not None and (len(line) - len(line.lstrip())) > last_indent:
                blanks_since_last_item = 0
                continue
            close_group()
            last_indent = None
            blanks_since_last_item = 0

    close_group()

    findings: list[str] = []
    for g in groups:
        if len(g) < 2:
            continue
        # blanks_before for items[1:] tells us separation between adjacent items.
        seps = [item["blanks_before"] for item in g[1:]]
        has_blank = any(s >= 1 for s in seps)
        has_tight = any(s == 0 for s in seps)
        if has_blank and has_tight:
            first_line = g[0]["line"]
            last_line = g[-1]["line"]
            tight_pairs = sum(1 for s in seps if s == 0)
            loose_pairs = sum(1 for s in seps if s >= 1)
            findings.append(
                f"lines {first_line}-{last_line}: list group has mixed item "
                f"separation ({loose_pairs} loose pair(s), {tight_pairs} "
                f"tight pair(s)) at indent {g[0]['indent']}"
            )

    if findings:
        for f in findings:
            print(f)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
