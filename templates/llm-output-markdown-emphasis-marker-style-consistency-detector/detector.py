#!/usr/bin/env python3
"""Detect mixed emphasis-marker styles (*em* vs _em_) within a single Markdown document.

Both `*word*` and `_word_` render as italic emphasis. A clean document should
pick one. Mixing them within a single file is a common LLM stitching artifact.

This detector targets *single-marker* emphasis only. Bold (`**` / `__`) is
handled by a separate detector and is explicitly ignored here.

Exit codes:
  0 -- consistent (or fewer than 2 emphasis spans found)
  1 -- mixed styles detected
  2 -- usage error
"""
from __future__ import annotations

import re
import sys
from collections import defaultdict
from pathlib import Path

# Match a single-* emphasis span that is NOT part of a ** bold marker.
# Use lookarounds to ensure the marker is exactly one char.
STAR = re.compile(r"(?<![*\w])\*(?!\s)(?!\*)([^*\n]+?)(?<!\s)\*(?!\*)(?!\w)")
UNDER = re.compile(r"(?<![_\w])_(?!\s)(?!_)([^_\n]+?)(?<!\s)_(?!_)(?!\w)")


def strip_code(line: str) -> str:
    """Blank out inline-code spans so backtick contents don't trigger matches."""
    return re.sub(r"`[^`\n]*`", lambda m: " " * len(m.group(0)), line)


def scan(path: Path) -> tuple[dict[str, list[tuple[int, str]]], list[str]]:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    findings: dict[str, list[tuple[int, str]]] = defaultdict(list)
    in_fence = False
    fence_marker = ""

    for idx, raw in enumerate(lines, start=1):
        stripped_lead = raw.lstrip()
        if not in_fence and (stripped_lead.startswith("```") or stripped_lead.startswith("~~~")):
            in_fence = True
            fence_marker = stripped_lead[:3]
            continue
        if in_fence:
            if stripped_lead.startswith(fence_marker):
                in_fence = False
            continue

        line = strip_code(raw)
        for m in STAR.finditer(line):
            findings["star"].append((idx, m.group(0)))
        for m in UNDER.finditer(line):
            findings["under"].append((idx, m.group(0)))
    return findings, lines


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: detector.py <markdown-file>", file=sys.stderr)
        return 2
    path = Path(argv[1])
    if not path.is_file():
        print(f"error: not a file: {path}", file=sys.stderr)
        return 2
    findings, _ = scan(path)
    used = [k for k, v in findings.items() if v]
    if len(used) < 2:
        total = sum(len(v) for v in findings.values())
        print(f"OK: {path} uses a consistent emphasis style ({total} span(s)).")
        return 0
    counts = {k: len(findings[k]) for k in used}
    minority = min(counts, key=counts.get)
    majority = max(counts, key=counts.get)
    print(f"FAIL: {path} mixes emphasis styles: {counts}")
    print(f"  majority: {majority} ({counts[majority]}); minority: {minority} ({counts[minority]})")
    flat: list[tuple[int, str, str]] = []
    for kind, items in findings.items():
        for line_no, text in items:
            flat.append((line_no, kind, text))
    flat.sort()
    for line_no, kind, text in flat:
        print(f"  line {line_no} [{kind}]: {text}")
    print(f"findings: {len(flat)}")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
