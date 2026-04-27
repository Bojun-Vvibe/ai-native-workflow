#!/usr/bin/env python3
"""Detect mixed horizontal-rule styles (---, ***, ___) within a single Markdown document.

A clean document should pick ONE thematic-break style and stick to it. Mixing
them is a common LLM artifact when stitching multiple drafts together.

Exit codes:
  0 -- no findings (zero or one HR style used)
  1 -- mixed styles detected
  2 -- usage error
"""
from __future__ import annotations

import re
import sys
from collections import defaultdict
from pathlib import Path

# An HR line is a line containing only 3+ of -, *, or _ (optionally separated by spaces).
HR_DASH = re.compile(r"^\s{0,3}(-\s*){3,}$")
HR_STAR = re.compile(r"^\s{0,3}(\*\s*){3,}$")
HR_UNDER = re.compile(r"^\s{0,3}(_\s*){3,}$")


def classify(line: str) -> str | None:
    if HR_DASH.match(line):
        # Avoid setext heading underlines (--- following a non-blank line is a
        # setext heading, not a thematic break). The caller handles context.
        return "dash"
    if HR_STAR.match(line):
        return "star"
    if HR_UNDER.match(line):
        return "under"
    return None


def scan(path: Path) -> list[tuple[int, str, str]]:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    findings: list[tuple[int, str, str]] = []
    in_fence = False
    fence_marker = ""
    seen: dict[str, list[int]] = defaultdict(list)

    for idx, line in enumerate(lines, start=1):
        stripped = line.lstrip()
        # Track fenced code blocks; ignore everything inside them.
        if not in_fence and (stripped.startswith("```") or stripped.startswith("~~~")):
            in_fence = True
            fence_marker = stripped[:3]
            continue
        if in_fence:
            if stripped.startswith(fence_marker):
                in_fence = False
            continue

        kind = classify(line)
        if kind is None:
            continue
        # Setext heading underline: previous non-blank line is text and current
        # line is dash-only. Only matters for "dash" because setext uses === or ---.
        if kind == "dash" and idx >= 2:
            prev = lines[idx - 2].strip()
            if prev and not classify(lines[idx - 2]):
                # Looks like a setext H2 underline; skip.
                continue
        seen[kind].append(idx)

    if len(seen) > 1:
        for kind, line_nums in seen.items():
            for n in line_nums:
                findings.append((n, kind, lines[n - 1].strip()))
    return findings


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: detector.py <markdown-file>", file=sys.stderr)
        return 2
    path = Path(argv[1])
    if not path.is_file():
        print(f"error: not a file: {path}", file=sys.stderr)
        return 2
    findings = scan(path)
    if not findings:
        print(f"OK: {path} uses a consistent horizontal-rule style.")
        return 0
    findings.sort()
    styles = sorted({k for _, k, _ in findings})
    print(f"FAIL: {path} mixes {len(styles)} horizontal-rule styles: {', '.join(styles)}")
    for line_no, kind, content in findings:
        print(f"  line {line_no} [{kind}]: {content}")
    print(f"findings: {len(findings)}")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
