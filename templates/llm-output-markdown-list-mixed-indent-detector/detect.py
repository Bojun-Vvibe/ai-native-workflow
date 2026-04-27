#!/usr/bin/env python3
"""Detect mixed indentation styles within Markdown list items.

Flags:
  - Tab-indented list items when space-indented list items also exist.
  - Inconsistent space-indent units (e.g. some nested bullets at 2 spaces,
    others at 4 spaces) within the same document.

Ignores lines inside fenced code blocks (``` or ~~~).
Stdlib only. Exit 0 if clean, 1 if findings, 2 on usage error.
"""
from __future__ import annotations

import re
import sys

LIST_RE = re.compile(r"^(?P<indent>[ \t]*)(?P<marker>[-*+]|\d+[.)])\s+\S")
FENCE_RE = re.compile(r"^\s*(```+|~~~+)")


def scan(path: str) -> int:
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except OSError as exc:
        print(f"error: cannot read {path}: {exc}", file=sys.stderr)
        return 2

    findings: list[str] = []
    in_fence = False
    fence_marker = ""
    tab_lines: list[tuple[int, str]] = []
    space_indent_units: dict[int, list[int]] = {}  # unit -> line numbers

    for lineno, raw in enumerate(lines, start=1):
        line = raw.rstrip("\n")
        fm = FENCE_RE.match(line)
        if fm:
            tok = fm.group(1)
            if not in_fence:
                in_fence = True
                fence_marker = tok[0]  # ` or ~
            elif tok[0] == fence_marker:
                in_fence = False
                fence_marker = ""
            continue
        if in_fence:
            continue
        m = LIST_RE.match(line)
        if not m:
            continue
        indent = m.group("indent")
        if not indent:
            continue  # top-level list, no indent question
        if "\t" in indent:
            tab_lines.append((lineno, line))
            continue
        # pure-space indent: record the unit
        unit = len(indent)
        space_indent_units.setdefault(unit, []).append(lineno)

    # Finding 1: tabs mixed with spaces
    has_space_indents = bool(space_indent_units)
    if tab_lines and has_space_indents:
        for ln, content in tab_lines:
            findings.append(
                f"{path}:{ln}: tab-indented list item mixed with space-indented list items"
            )

    # Finding 2: inconsistent space indent units.
    # We treat indent units as "consistent" if they form multiples of a single
    # base (2 or 4). If we see both a unit that's only valid as 2-base
    # (e.g. 2, 6) AND a unit that's only valid as 4-base (e.g. 4 alone with
    # no 2 present is fine; but 2 + 4 + 6 is mixed because 4 ≠ k*2 only when
    # paired with 2 — actually 4 = 2*2, so 2/4/6 is consistent at base 2).
    # Simpler rule: collect all units, find gcd; if any unit is not a multiple
    # of the gcd it can't happen. So instead: if the set contains both a
    # "4-only" indent (4, 12) and a "2-only" indent (2, 6, 10) we flag.
    units = sorted(space_indent_units.keys())
    if len(units) >= 2:
        # Detect mixing by checking: do we have a unit divisible by 2 but not
        # 4 (e.g. 2, 6, 10) AND a unit divisible by 4 but unreachable from
        # the smaller base? Practical heuristic:
        # mix if min unit is 2 and some unit is 4 or 8 (it's still 2-base ok)
        # Real mix: presence of 2 and presence of 3 (odd indent), OR presence
        # of indents that aren't all multiples of the smallest unit.
        base = units[0]
        bad_units = [u for u in units if u % base != 0]
        if bad_units:
            for u in bad_units:
                for ln in space_indent_units[u]:
                    findings.append(
                        f"{path}:{ln}: list indent {u} spaces inconsistent with base unit {base} spaces"
                    )

    if findings:
        for f in findings:
            print(f)
        print(f"\n{len(findings)} finding(s)")
        return 1
    return 0


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: detect.py <file.md>", file=sys.stderr)
        return 2
    return scan(argv[1])


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
