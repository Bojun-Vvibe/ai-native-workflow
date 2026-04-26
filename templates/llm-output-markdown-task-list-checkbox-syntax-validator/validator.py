#!/usr/bin/env python3
"""
Markdown task-list checkbox syntax validator.

Detects malformed GFM task list items in LLM output. A valid task list item
looks like:

    - [ ] todo
    - [x] done
    * [X] done (capital X also valid)
    1. [ ] numbered todo

Common LLM mistakes this catches:
  * `- []` (no space inside brackets)
  * `- [ ]no-space-after` (missing space after closing bracket)
  * `- [y] foo` (non-standard mark; only space, x, X allowed)
  * `- [  ] foo` (two spaces inside brackets)
  * `- [ x ] foo` (padded mark)
  * `-[ ] foo` (no space between bullet and bracket)

Stdin or file path. Exit 0 if clean, 1 if any defect found.
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass

# A line that *looks* like an attempted task list item: bullet/number, then
# something resembling brackets near the start. We match loosely on purpose so
# we catch malformed attempts.
ATTEMPT_RE = re.compile(
    r"^(?P<indent>\s*)(?P<bullet>[-*+]|\d+\.)(?P<gap>\s*)\[(?P<inner>[^\]]{0,5})\](?P<after>.?)"
)

# Strict, well-formed task list item.
STRICT_RE = re.compile(
    r"^\s*(?:[-*+]|\d+\.)\s\[[ xX]\]\s\S"
)


@dataclass
class Defect:
    line_no: int
    line: str
    reason: str


def scan(text: str) -> list[Defect]:
    defects: list[Defect] = []
    for i, raw in enumerate(text.splitlines(), start=1):
        m = ATTEMPT_RE.match(raw)
        if not m:
            continue
        # If it matches strict, it's fine.
        if STRICT_RE.match(raw):
            continue
        # Diagnose why it failed.
        gap = m.group("gap")
        inner = m.group("inner")
        after = m.group("after")
        bullet = m.group("bullet")

        if gap == "":
            defects.append(Defect(i, raw, f"missing space between bullet '{bullet}' and '['"))
            continue
        if inner == "":
            defects.append(Defect(i, raw, "empty brackets '[]' (need ' ', 'x', or 'X')"))
            continue
        if inner not in (" ", "x", "X"):
            defects.append(Defect(i, raw, f"invalid checkbox mark {inner!r} (only ' ', 'x', 'X' allowed)"))
            continue
        if after == "":
            defects.append(Defect(i, raw, "no content after ']' (line ends at bracket)"))
            continue
        if not after.isspace():
            defects.append(Defect(i, raw, f"missing space after ']' (got {after!r})"))
            continue
        # Fallthrough: looked like a task list item but failed strict for an
        # unclassified reason — flag conservatively.
        defects.append(Defect(i, raw, "malformed task list item"))
    return defects


def main(argv: list[str]) -> int:
    if len(argv) > 1 and argv[1] != "-":
        with open(argv[1], encoding="utf-8") as f:
            text = f.read()
    else:
        text = sys.stdin.read()
    defects = scan(text)
    for d in defects:
        print(f"line {d.line_no}: {d.reason}")
        print(f"  > {d.line}")
    if defects:
        print(f"\nFAIL: {len(defects)} malformed task list item(s)")
        return 1
    print("OK: all task list items well-formed")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
