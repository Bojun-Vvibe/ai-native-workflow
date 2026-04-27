#!/usr/bin/env python3
"""Validate GFM strikethrough tilde counts in Markdown.

GitHub-Flavored Markdown strikethrough is exactly two tildes on each side:
``~~text~~``. LLMs frequently emit:

  * ``~text~``       (one tilde — not strikethrough in GFM)
  * ``~~~text~~~``   (three tildes — collides with fence syntax)
  * ``~~text~``      (mismatched closing run)
  * ``~text~~``      (mismatched opening run)

This linter scans non-fence text for runs of 1-N tildes and pairs them up
to flag any pair whose run lengths are not exactly (2, 2).

Lines inside fenced code blocks (``` or ~~~) are ignored.

Stdlib only. Exit 0 if clean, 1 if findings, 2 on usage error.
"""
from __future__ import annotations

import re
import sys

# Match a non-fence run of tildes that is part of inline content. We exclude
# tilde runs that constitute a code fence opener/closer themselves; those are
# handled by the fence state machine before we get here.
TILDE_RUN_RE = re.compile(r"~+")
FENCE_RE = re.compile(r"^\s*(```+|~~~+)\s*\S*\s*$")


def find_pairs(line: str) -> list[tuple[int, int, int, int]]:
    """Return list of (open_col, open_len, close_col, close_len) for tilde
    pairs on the line. Open/close are paired greedily left-to-right.

    Single unpaired runs are returned with close_col=-1 so the caller can
    flag them separately.
    """
    runs = [(m.start(), len(m.group(0))) for m in TILDE_RUN_RE.finditer(line)]
    pairs: list[tuple[int, int, int, int]] = []
    i = 0
    while i < len(runs):
        if i + 1 < len(runs):
            o_col, o_len = runs[i]
            c_col, c_len = runs[i + 1]
            pairs.append((o_col, o_len, c_col, c_len))
            i += 2
        else:
            o_col, o_len = runs[i]
            pairs.append((o_col, o_len, -1, 0))
            i += 1
    return pairs


def scan(path: str) -> int:
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except OSError as exc:
        print(f"error: cannot read {path}: {exc}", file=sys.stderr)
        return 2

    findings: list[str] = []
    in_fence = False
    fence_char = ""

    for lineno, raw in enumerate(lines, start=1):
        line = raw.rstrip("\n")

        # Code fence handling: a line that is ONLY a fence opener/closer.
        fm = FENCE_RE.match(line)
        if fm:
            tok = fm.group(1)
            if not in_fence:
                in_fence = True
                fence_char = tok[0]
            elif tok[0] == fence_char:
                in_fence = False
                fence_char = ""
            continue
        if in_fence:
            continue

        # Skip lines whose only tildes are nothing (fast path)
        if "~" not in line:
            continue

        for o_col, o_len, c_col, c_len in find_pairs(line):
            if c_col == -1:
                # Lonely tilde run — usually a mistake in inline strikethrough
                findings.append(
                    f"{path}:{lineno}:{o_col + 1}: unpaired tilde run of length {o_len}"
                )
                continue
            if o_len == 2 and c_len == 2:
                continue  # canonical ~~text~~
            findings.append(
                f"{path}:{lineno}:{o_col + 1}: strikethrough tilde count mismatch "
                f"(open={o_len}, close={c_len}); expected (2, 2)"
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
