#!/usr/bin/env python3
"""Detect trailing whitespace on the *info string* of a fenced code block opener.

A fenced code opener like ```` ```python ```` may have an info string after the
fence chars. CommonMark trims it, so renderers don't visibly care, but trailing
whitespace on the info string is a strong LLM artifact:

  - The model emitted ```` ```python ```` followed by a trailing space before the
    newline (often when re-streaming after a stop token).
  - A repair pass appended a comment or attribute and then deleted it without
    trimming the leftover space.
  - Hand-written CommonMark almost never has this; tooling-canonical output
    almost never has this; LLM output frequently does.

Trailing whitespace on info strings also breaks naive consumers that key off
the raw info string (e.g. `info == "python"` checks) and confuses syntax
highlighters that look at the literal token after the fence.

Strategy
--------
- Scan line by line.
- A fenced code *opener* is a line whose lstripped prefix is ``` or ~~~ (3+),
  outside any currently-open fence. The remainder after the fence chars is the
  info string.
- If the info string is non-empty AND has trailing space/tab characters before
  the line ending, flag it.
- Track fence open/close so we don't scan content lines.
- Empty info strings (``` alone) are ignored — there is nothing to trim.
- Closing fences are never info-string-bearing in CommonMark; we ignore any
  trailing whitespace on the close line (it's a separate lint).

Exit codes
----------
  0 = clean
  1 = at least one trailing-space info string found
  2 = usage / IO error
"""
from __future__ import annotations

import sys
from pathlib import Path


def find_findings(text: str) -> list[tuple[int, int, str, str]]:
    """Return list of (lineno, col_1based_of_first_trailing_ws, fence_chars, info_string_repr).

    `info_string_repr` is the raw info string (with the trailing whitespace
    preserved) so the report is self-explanatory.
    """
    findings: list[tuple[int, int, str, str]] = []
    in_fence = False
    open_fence_char = ""
    open_fence_len = 0

    for lineno, raw in enumerate(text.splitlines(), start=1):
        # Strip up to 3 leading spaces per CommonMark (indented code rules).
        stripped = raw.lstrip(" ")
        leading = len(raw) - len(stripped)
        if leading > 3:
            # Anything indented 4+ inside a paragraph is not a fence; but for
            # safety just treat as content line.
            continue

        # Determine if this line is a fence line (opener or closer).
        fence_char = ""
        if stripped.startswith("```"):
            fence_char = "`"
        elif stripped.startswith("~~~"):
            fence_char = "~"

        if not in_fence:
            if not fence_char:
                continue
            # Count fence chars
            i = 0
            while i < len(stripped) and stripped[i] == fence_char:
                i += 1
            fence_len = i
            if fence_len < 3:
                continue
            info = stripped[fence_len:]  # raw info string (incl. trailing ws/newline-stripped)
            # Backtick-fenced openers cannot contain a backtick in the info string.
            if fence_char == "`" and "`" in info:
                continue
            # Open the fence.
            in_fence = True
            open_fence_char = fence_char
            open_fence_len = fence_len

            # Now check for trailing whitespace on a non-empty info string.
            if not info:
                continue
            stripped_info = info.rstrip(" \t")
            if stripped_info == info:
                continue  # no trailing ws
            if not stripped_info:
                # Info string was *all* whitespace -> CommonMark treats as no
                # info string. Still a tell, but a different lint; skip here.
                continue
            # Column where the first trailing ws character appears (1-based, in raw line)
            # raw line layout: [leading spaces][fence chars][info...]
            col = leading + fence_len + len(stripped_info) + 1
            findings.append((lineno, col, fence_char * fence_len, info))
        else:
            # We're inside a fence; only an exact-or-longer matching fence can close it,
            # and the close line must have NO info string.
            if not fence_char or fence_char != open_fence_char:
                continue
            i = 0
            while i < len(stripped) and stripped[i] == fence_char:
                i += 1
            close_len = i
            if close_len < open_fence_len:
                continue
            tail = stripped[close_len:]
            # CommonMark: a closing fence may be followed only by spaces/tabs.
            if tail.strip(" \t") != "":
                continue
            in_fence = False
            open_fence_char = ""
            open_fence_len = 0

    return findings


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(f"usage: {argv[0]} <file.md> [<file2.md> ...]", file=sys.stderr)
        return 2

    any_hits = False
    for arg in argv[1:]:
        path = Path(arg)
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        findings = find_findings(text)
        for lineno, col, fence, info in findings:
            # Render info with trailing ws made visible
            visible = info.replace("\t", "\\t")
            print(
                f"{path}:{lineno}:{col}: fenced-code-info-string-trailing-space "
                f"(fence={fence}, info={visible!r})"
            )
        if findings:
            any_hits = True

    return 1 if any_hits else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
