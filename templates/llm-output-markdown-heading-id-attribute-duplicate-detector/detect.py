#!/usr/bin/env python3
"""Detect duplicate heading id attributes in Markdown.

Pandoc / kramdown / many static-site generators support an explicit
heading id syntax:

    ## Heading text {#custom-id}

The id becomes the URL fragment for in-page anchor links. If the same
id appears on two headings in one document:

* in-page links to ``#custom-id`` resolve non-deterministically
  (browsers usually pick the first match, but tooling like
  link-checkers may flag the second)
* generated tables of contents collapse the two entries
* downstream tools that index headings by id (search, breadcrumbs)
  silently lose one of the entries

LLMs reuse boilerplate slugs (`#overview`, `#summary`, `#example`)
across regenerated sections, so this defect appears regularly in
machine-assembled documents.

The detector is **code-fence-aware**: heading-shaped lines inside a
fenced code block are skipped, so a tutorial that quotes
``## Foo {#bar}`` inside a ``` fence does not produce false positives.

Exit codes:
  0 — clean
  1 — findings
  2 — usage error
"""
from __future__ import annotations

import re
import sys
from typing import Iterable

# ATX heading: 1-6 leading hashes, space, text, optional {#id} suffix.
ATX_RE = re.compile(
    r"^(\s{0,3})(#{1,6})\s+(.*?)\s*(?:\{\s*#([A-Za-z0-9_\-:.]+)\s*\})\s*#*\s*$"
)
FENCE_RE = re.compile(r"^(\s{0,3})(`{3,}|~{3,})\s*([^\s`]*)")


def find_id_attributes(lines: Iterable[str]) -> list[tuple[int, str]]:
    """Yield (lineno, id) for every ATX heading with an explicit id,
    skipping anything inside an open fenced code block.
    """
    out: list[tuple[int, str]] = []
    in_fence = False
    open_marker_char = ""
    open_marker_len = 0
    for i, raw in enumerate(lines, start=1):
        line = raw.rstrip("\n")
        fm = FENCE_RE.match(line)
        if fm:
            marker = fm.group(2)
            info = fm.group(3)
            if not in_fence:
                in_fence = True
                open_marker_char = marker[0]
                open_marker_len = len(marker)
            else:
                if (
                    marker[0] == open_marker_char
                    and len(marker) >= open_marker_len
                    and info == ""
                ):
                    in_fence = False
                    open_marker_char = ""
                    open_marker_len = 0
            continue
        if in_fence:
            continue
        m = ATX_RE.match(line)
        if not m:
            continue
        out.append((i, m.group(4)))
    return out


def detect(path: str) -> int:
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.readlines()
    except OSError as e:
        print(f"error: cannot read {path}: {e}", file=sys.stderr)
        return 2

    seen: dict[str, int] = {}
    findings = 0
    for lineno, hid in find_id_attributes(lines):
        if hid in seen:
            print(
                f"{path}:{lineno}:1: duplicate heading id "
                f"'{{#{hid}}}' — first defined at line {seen[hid]}"
            )
            findings += 1
        else:
            seen[hid] = lineno

    if findings:
        print(f"\n{findings} finding(s)")
        return 1
    return 0


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: detect.py <markdown-file>", file=sys.stderr)
        return 2
    return detect(argv[1])


if __name__ == "__main__":
    sys.exit(main(sys.argv))
