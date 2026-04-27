#!/usr/bin/env python3
"""Detect hard tab characters in Markdown outside of fenced code blocks.

Equivalent to markdownlint MD010 (no-hard-tabs).

Exit codes:
  0 = no hard tabs found outside code fences
  1 = hard tab(s) found
  2 = usage / IO error
"""
from __future__ import annotations

import sys
from pathlib import Path


FENCE_CHARS = ("```", "~~~")


def find_hard_tabs(text: str) -> list[tuple[int, int]]:
    """Return list of (line_no_1based, col_1based) for hard tabs outside fences."""
    hits: list[tuple[int, int]] = []
    in_fence = False
    fence_marker = ""

    for lineno, line in enumerate(text.splitlines(), start=1):
        stripped = line.lstrip()
        # Detect fence open/close. A fence line starts with ``` or ~~~.
        if not in_fence:
            for marker in FENCE_CHARS:
                if stripped.startswith(marker):
                    in_fence = True
                    fence_marker = marker
                    break
            # Don't flag tabs on the fence-open line itself
            if in_fence:
                continue
        else:
            if stripped.startswith(fence_marker):
                in_fence = False
                fence_marker = ""
            # While inside fence (including the close line), skip
            continue

        # Outside fence — scan for tabs
        idx = line.find("\t")
        while idx != -1:
            hits.append((lineno, idx + 1))
            idx = line.find("\t", idx + 1)

    return hits


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(f"usage: {argv[0]} <file.md>", file=sys.stderr)
        return 2

    path = Path(argv[1])
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    hits = find_hard_tabs(text)
    for lineno, col in hits:
        print(f"{path}:{lineno}:{col}: MD010 hard tab outside fenced code block")

    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
