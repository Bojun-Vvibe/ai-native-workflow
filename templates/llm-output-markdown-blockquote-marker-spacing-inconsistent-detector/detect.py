#!/usr/bin/env python3
"""Detect inconsistent spacing after blockquote `>` markers within a single document.

CommonMark allows `>foo`, `> foo`, and (unusually) `>  foo`. Mixing these in
one document is almost always an LLM artifact — humans reach for one style
and stick with it.

Strategy:
  - Scan all blockquote lines outside fenced code blocks.
  - Classify each `>` marker's trailing spacing into one of:
      "none"     -> `>foo` (zero spaces after >)
      "one"      -> `> foo` (exactly one space)
      "many"     -> `>  foo` or more
      "empty"    -> `>` alone or `> ` (whitespace only) — ignored from the
                    style vote, since these are blank quote lines
  - If more than one of {"none","one","many"} appears in the same file, every
    line whose style is NOT the dominant (most-frequent) style is flagged.
  - Nested markers (`>>`, `> >`) are normalized: only the *innermost* marker's
    trailing spacing is examined.

Exit codes:
  0 = consistent (or no blockquotes)
  1 = inconsistent spacing found
  2 = usage / IO error
"""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path


FENCE_CHARS = ("```", "~~~")


def classify(line: str) -> tuple[int, str | None]:
    """Return (innermost_marker_end_col_1based, style) for a blockquote line.

    Returns (0, None) for non-blockquote lines.
    """
    # A blockquote line, after optional up-to-3-space indent, starts with `>`.
    i = 0
    n = len(line)
    # Skip up to 3 leading spaces (CommonMark)
    spaces = 0
    while i < n and line[i] == " " and spaces < 3:
        i += 1
        spaces += 1
    if i >= n or line[i] != ">":
        return 0, None

    # Walk through nested `>` markers; spaces between markers are allowed.
    last_marker_idx = -1
    while i < n and line[i] == ">":
        last_marker_idx = i
        i += 1
        # Allow one optional space between nested markers, then continue if next is `>`
        j = i
        while j < n and line[j] == " ":
            j += 1
        if j < n and line[j] == ">":
            i = j
            continue
        else:
            break

    # Now classify spacing after last_marker_idx
    after = line[last_marker_idx + 1 :]
    if after == "" or after.strip() == "":
        return last_marker_idx + 1, "empty"
    if after.startswith("  "):
        return last_marker_idx + 1, "many"
    if after.startswith(" "):
        return last_marker_idx + 1, "one"
    return last_marker_idx + 1, "none"


def find_inconsistent(text: str) -> tuple[list[tuple[int, str, str]], str | None]:
    """Return (hits, dominant_style).

    hits = list of (lineno, observed_style, dominant_style).
    """
    in_fence = False
    fence_marker = ""
    classifications: list[tuple[int, str]] = []  # (lineno, style)

    for lineno, line in enumerate(text.splitlines(), start=1):
        stripped = line.lstrip()
        if not in_fence:
            for marker in FENCE_CHARS:
                if stripped.startswith(marker):
                    in_fence = True
                    fence_marker = marker
                    break
            if in_fence:
                continue
        else:
            if stripped.startswith(fence_marker):
                in_fence = False
                fence_marker = ""
            continue

        _, style = classify(line)
        if style is None or style == "empty":
            continue
        classifications.append((lineno, style))

    if not classifications:
        return [], None

    counts = Counter(s for _, s in classifications)
    if len(counts) <= 1:
        return [], next(iter(counts), None)

    # Dominant = most common; ties broken by preferring "one" (the canonical
    # CommonMark style), then "none", then "many".
    pref = {"one": 0, "none": 1, "many": 2}
    dominant = sorted(
        counts.items(), key=lambda kv: (-kv[1], pref.get(kv[0], 99))
    )[0][0]

    hits = [(ln, s, dominant) for ln, s in classifications if s != dominant]
    return hits, dominant


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

    hits, dominant = find_inconsistent(text)
    for lineno, observed, dom in hits:
        print(
            f"{path}:{lineno}:1: blockquote-marker-spacing-inconsistent "
            f"(observed={observed}, dominant={dom})"
        )

    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
