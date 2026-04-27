#!/usr/bin/env python3
"""Detect blank lines that fragment a Markdown blockquote.

Pattern flagged:

    > first paragraph of the quote.
    >
    > second paragraph — but a *truly* blank line between
                                                                              them
    > would terminate the quote.

CommonMark treats a `>` line followed by a fully blank line (no `>`) as the
end of the blockquote. LLMs often emit this accidentally because they think
visual whitespace = paragraph break inside the quote, when in fact it splits
the quote into two adjacent quotes (or a quote followed by a paragraph).

We flag any blank line ("" after rstrip) that sits *between* two `>`-prefixed
lines, because the author almost certainly meant a continuous quote.

Code-fence aware: skip lines inside ``` / ~~~ fences.

Exit codes:
  0 = no fragmenting blank lines
  1 = one or more fragmenting blank lines found
  2 = usage / IO error
"""
from __future__ import annotations

import sys
from pathlib import Path


FENCE_CHARS = ("```", "~~~")


def is_blockquote_line(line: str) -> bool:
    stripped = line.lstrip(" ")
    # Allow up to 3 leading spaces per CommonMark, then `>`.
    if len(line) - len(stripped) > 3:
        return False
    return stripped.startswith(">")


def find_fragmenting_blanks(text: str) -> list[tuple[int, str]]:
    """Return list of (lineno_1based, message) for blank lines splitting a quote."""
    lines = text.splitlines()
    hits: list[tuple[int, str]] = []
    in_fence = False
    fence_marker = ""

    # First pass: mark fence regions to ignore.
    fence_mask = [False] * len(lines)
    for i, line in enumerate(lines):
        stripped = line.lstrip()
        if not in_fence:
            for marker in FENCE_CHARS:
                if stripped.startswith(marker):
                    in_fence = True
                    fence_marker = marker
                    fence_mask[i] = True
                    break
        else:
            fence_mask[i] = True
            if stripped.startswith(fence_marker):
                in_fence = False
                fence_marker = ""

    for i, line in enumerate(lines):
        if fence_mask[i]:
            continue
        if line.rstrip() != "":
            continue
        # blank line — check neighbors
        prev_idx = i - 1
        next_idx = i + 1
        if prev_idx < 0 or next_idx >= len(lines):
            continue
        if fence_mask[prev_idx] or fence_mask[next_idx]:
            continue
        if is_blockquote_line(lines[prev_idx]) and is_blockquote_line(lines[next_idx]):
            hits.append(
                (
                    i + 1,
                    "blank line between two blockquote lines fragments the quote; "
                    "use '>' (a bare-marker line) to keep the quote continuous",
                )
            )
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

    hits = find_fragmenting_blanks(text)
    for lineno, msg in hits:
        print(f"{path}:{lineno}: {msg}")

    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
