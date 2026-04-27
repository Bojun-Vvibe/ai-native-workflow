#!/usr/bin/env python3
"""Detect ATX headings with more than one space between the hash run
and the heading text (or before a closing-hash sequence).

CommonMark requires *at least one* space after the opening `#` run, but
LLMs frequently emit two-or-more spaces — usually because the model
visually padded the heading to align with surrounding text. Most
renderers happily eat the extra spaces, but lint tools catch them
(markdownlint MD019 for headings without a closing-hash, MD021 for
"closed" ATX headings such as `## Heading ##`).

Both classes are flagged separately so downstream tooling can
distinguish them:

- ``extra_space_after_open`` — more than one space between the opening
  hash run and the first non-space character of the heading text.
- ``extra_space_before_close`` — for closed ATX headings, more than
  one space between the heading text and the closing hash run.

Reads stdin, writes findings to stdout, exits ``1`` on any finding,
``0`` on a clean document. Fenced code blocks (``` ``` ``` /
``~~~``) are skipped.
"""

from __future__ import annotations

import re
import sys

FENCE_RE = re.compile(r"^\s*(```|~~~)")

# ATX heading anatomy:
#   leading_indent (0-3 spaces)
#   open_hashes    (#, ##, ###, ####, #####, ######)
#   open_spaces    (1+ spaces or tabs — required by spec)
#   content_and_close (everything else)
#
# The heading may end with a closing run of `#`s preceded by 1+ spaces;
# everything after that run (just trailing whitespace) is allowed.
ATX_RE = re.compile(
    r"^(?P<indent> {0,3})"
    r"(?P<hashes>#{1,6})"
    r"(?P<after>[ \t]+)"
    r"(?P<rest>.*?)"
    r"\s*$"
)

# Inside `rest`, look for an optional closing run: 1+ spaces/tabs, then
# 1+ `#`s, then only whitespace. We split rest into (text, gap, close).
CLOSE_RE = re.compile(r"^(?P<text>.*?)(?P<gap>[ \t]+)(?P<close>#+)\s*$")


def main() -> int:
    lines = sys.stdin.read().splitlines()
    in_fence = False
    findings: list[str] = []

    for idx, line in enumerate(lines, start=1):
        if FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue

        m = ATX_RE.match(line)
        if not m:
            continue
        # Empty heading (`#` with nothing after) does not match because
        # `after` requires 1+ spaces and `.*?` against empty rest with
        # trailing `\s*$` only matches if rest is non-empty after the
        # required space. That is fine: empty headings are a separate
        # finding class handled elsewhere.
        rest = m.group("rest")
        if not rest:
            continue

        level = len(m.group("hashes"))
        after_spaces = len(m.group("after"))

        # Decide whether this is a closed ATX heading.
        cm = CLOSE_RE.match(rest)
        if cm:
            text = cm.group("text").rstrip()
            gap = cm.group("gap")
            close_run = cm.group("close")
            preview = text[:50]
            if after_spaces > 1:
                findings.append(
                    f"line {idx}: closed ATX heading (h{level}) has "
                    f"{after_spaces} spaces after opening hashes "
                    f"(expected 1): {preview!r}"
                )
            if len(gap) > 1:
                findings.append(
                    f"line {idx}: closed ATX heading (h{level}) has "
                    f"{len(gap)} spaces before closing {close_run!r} "
                    f"(expected 1): {preview!r}"
                )
        else:
            text = rest.rstrip()
            preview = text[:50]
            if after_spaces > 1:
                findings.append(
                    f"line {idx}: ATX heading (h{level}) has "
                    f"{after_spaces} spaces after opening hashes "
                    f"(expected 1): {preview!r}"
                )

    if findings:
        for f in findings:
            print(f)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
