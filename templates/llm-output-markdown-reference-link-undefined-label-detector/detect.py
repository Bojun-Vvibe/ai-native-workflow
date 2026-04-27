#!/usr/bin/env python3
"""Detect reference-style Markdown links/images whose label has no matching definition.

A reference link looks like ``[text][label]`` or the shortcut ``[label][]`` /
``[label]``. A definition looks like ``[label]: https://example.com "title"`` at
the start of a line (optionally indented up to 3 spaces).

This detector flags any ``[text][label]`` or ``![alt][label]`` usage whose
``label`` (case-insensitive, whitespace-collapsed per CommonMark) has no
matching definition anywhere in the document.

Code-fence aware: occurrences inside ``` or ~~~ fences are ignored. Inline code
spans (single backticks) are also stripped before scanning each line.

Exit codes:
  0 = every reference label resolves
  1 = one or more undefined reference labels
  2 = usage / IO error
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


FENCE_CHARS = ("```", "~~~")

# Definition: optional 0-3 leading spaces, [label]:, then a destination.
DEF_RE = re.compile(r"^[ ]{0,3}\[([^\]]+)\]:\s*\S+")

# Full reference: [text][label]  -- label may be empty (collapsed form -> use text)
FULL_REF_RE = re.compile(r"(!?)\[([^\]]+)\]\[([^\]]*)\]")

# Shortcut reference: [label] not followed by ( or [ or :
# Conservative: only catch [label] followed by non-link punctuation/whitespace/EOL.
# To reduce false positives we DO NOT scan shortcut form; many plain "[text]"
# strings are not links. We only flag full and collapsed forms.


def normalize_label(label: str) -> str:
    """CommonMark label normalization: case-fold + collapse internal whitespace."""
    return re.sub(r"\s+", " ", label.strip()).lower()


def strip_inline_code(line: str) -> str:
    """Remove `...` inline code spans so brackets inside them aren't scanned."""
    # Non-greedy single-backtick spans. Doesn't try to match double-backtick spans
    # (rare in LLM output); good enough for detector purposes.
    return re.sub(r"`[^`\n]*`", "", line)


def collect_definitions(text: str) -> set[str]:
    defs: set[str] = set()
    in_fence = False
    fence_marker = ""
    for line in text.splitlines():
        stripped = line.lstrip()
        if not in_fence:
            for marker in FENCE_CHARS:
                if stripped.startswith(marker):
                    in_fence = True
                    fence_marker = marker
                    break
            if in_fence:
                continue
            m = DEF_RE.match(line)
            if m:
                defs.add(normalize_label(m.group(1)))
        else:
            if stripped.startswith(fence_marker):
                in_fence = False
                fence_marker = ""
    return defs


def find_undefined_refs(text: str) -> list[tuple[int, int, str, str]]:
    """Return list of (lineno, col, label_used, raw_match)."""
    defs = collect_definitions(text)
    hits: list[tuple[int, int, str, str]] = []
    in_fence = False
    fence_marker = ""

    for lineno, raw_line in enumerate(text.splitlines(), start=1):
        stripped = raw_line.lstrip()
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

        # Skip lines that are themselves definitions
        if DEF_RE.match(raw_line):
            continue

        scan_line = strip_inline_code(raw_line)
        for m in FULL_REF_RE.finditer(scan_line):
            text_part = m.group(2)
            label_part = m.group(3)
            # Collapsed form [text][] uses text as label
            label = label_part if label_part.strip() else text_part
            norm = normalize_label(label)
            if norm not in defs:
                hits.append((lineno, m.start() + 1, label, m.group(0)))

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

    hits = find_undefined_refs(text)
    for lineno, col, label, raw in hits:
        print(
            f"{path}:{lineno}:{col}: undefined reference label "
            f"{label!r} in {raw}"
        )

    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
