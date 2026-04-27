#!/usr/bin/env python3
"""Detect trailing blank lines inside fenced code blocks (just before the closing fence).

LLMs sometimes emit fenced code blocks like:

    ```python
    print("hi")


    ```

The two trailing blank lines inside the fence are almost never intentional —
they bloat code samples, confuse copy-paste, and shift line numbers in any
downstream tool that extracts the code. This detector flags any fenced code
block that has one or more blank lines immediately before its closing fence.

Exit codes:
  0 = no offending fences
  1 = at least one fence has trailing blank line(s)
  2 = usage / IO error / unclosed fence
"""
from __future__ import annotations

import sys
from pathlib import Path


FENCE_CHARS = ("```", "~~~")


def find_trailing_blank_in_fences(text: str) -> list[tuple[int, int, int]]:
    """Return list of (open_line, close_line, trailing_blank_count)."""
    hits: list[tuple[int, int, int]] = []
    in_fence = False
    fence_marker = ""
    open_line = 0
    trailing_blank = 0

    for lineno, line in enumerate(text.splitlines(), start=1):
        stripped = line.lstrip()
        if not in_fence:
            for marker in FENCE_CHARS:
                if stripped.startswith(marker):
                    in_fence = True
                    fence_marker = marker
                    open_line = lineno
                    trailing_blank = 0
                    break
            continue

        # Inside a fence
        if stripped.startswith(fence_marker):
            # Closing fence
            if trailing_blank > 0:
                hits.append((open_line, lineno, trailing_blank))
            in_fence = False
            fence_marker = ""
            trailing_blank = 0
            continue

        if line.strip() == "":
            trailing_blank += 1
        else:
            trailing_blank = 0

    if in_fence:
        # Unclosed fence — surface as error in main()
        hits.append((open_line, -1, -1))

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

    hits = find_trailing_blank_in_fences(text)
    real_hits = 0
    for open_line, close_line, blanks in hits:
        if close_line == -1:
            print(
                f"{path}:{open_line}:1: error unclosed fenced code block",
                file=sys.stderr,
            )
            return 2
        print(
            f"{path}:{close_line}:1: trailing-blank-lines-inside-fence "
            f"(fence opened at line {open_line}, {blanks} blank line(s) before close)"
        )
        real_hits += 1

    return 1 if real_hits else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
