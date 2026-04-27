#!/usr/bin/env python3
"""
llm-output-markdown-link-reference-style-mix-detector

Detects when a single Markdown document mixes inline link style
`[text](url)` with reference link style `[text][ref]` (or `[text][]`
or collapsed `[text]`).

LLM output often inconsistently switches between the two styles within
the same document, which is a low-grade quality smell. This detector
flags every link occurrence and reports the count of each style. It
exits 1 when BOTH styles are present (mix), 0 when only one style is
used (or no links at all).

Code-fence aware: links inside fenced code blocks (``` or ~~~) and
inline code spans (`...`) are ignored.

Exit codes:
  0 - clean (single style, or zero links)
  1 - mix detected
  2 - usage error
"""

from __future__ import annotations

import re
import sys
from typing import List, Tuple


FENCE_RE = re.compile(r"^(\s{0,3})(```+|~~~+)(.*)$")

# Link with inline destination: [text](dest)
# We require the closing bracket to be followed immediately by `(`.
INLINE_LINK_RE = re.compile(r"(?<!\!)\[([^\[\]\n]+)\]\(([^)\n]*)\)")

# Reference-style link: [text][ref], [text][], or shortcut [text]
# Must NOT be followed by `(` (that would be inline) or `:` (that would be a definition).
FULL_REF_RE = re.compile(r"(?<!\!)\[([^\[\]\n]+)\]\[([^\[\]\n]*)\]")
SHORTCUT_REF_RE = re.compile(r"(?<!\!)\[([^\[\]\n]+)\](?!\(|\[|:)")

# Reference link DEFINITION (excluded from "shortcut" matches): `[label]: url`
DEF_LINE_RE = re.compile(r"^\s{0,3}\[([^\[\]\n]+)\]:\s*\S+")


def strip_inline_code(line: str) -> str:
    """Replace inline `code spans` with spaces so links inside them are ignored."""
    out = []
    i = 0
    n = len(line)
    while i < n:
        if line[i] == "`":
            # Count backticks
            j = i
            while j < n and line[j] == "`":
                j += 1
            tick_run = line[i:j]
            # Look for matching closing run
            close = line.find(tick_run, j)
            if close == -1:
                out.append(line[i:])
                return "".join(out)
            out.append(" " * (close + len(tick_run) - i))
            i = close + len(tick_run)
        else:
            out.append(line[i])
            i += 1
    return "".join(out)


def is_definition_line(line: str) -> bool:
    return bool(DEF_LINE_RE.match(line))


def find_links(path: str) -> Tuple[List[Tuple[int, str, str]], int, int]:
    """Return (findings, inline_count, reference_count).

    findings: list of (line_no, style, snippet)
    """
    findings: List[Tuple[int, str, str]] = []
    inline_count = 0
    ref_count = 0

    in_fence = False
    fence_marker: str | None = None

    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for lineno, raw in enumerate(fh, start=1):
            line = raw.rstrip("\n")

            # Fence handling
            m = FENCE_RE.match(line)
            if m:
                marker = m.group(2)[0] * 3  # normalize to ``` / ~~~
                if not in_fence:
                    in_fence = True
                    fence_marker = marker
                    continue
                else:
                    if fence_marker and line.lstrip().startswith(fence_marker):
                        in_fence = False
                        fence_marker = None
                    continue

            if in_fence:
                continue

            if is_definition_line(line):
                # Reference DEFINITION, not a link usage. Skip.
                continue

            scrub = strip_inline_code(line)

            for m in INLINE_LINK_RE.finditer(scrub):
                inline_count += 1
                findings.append((lineno, "inline", m.group(0)))

            for m in FULL_REF_RE.finditer(scrub):
                ref_count += 1
                findings.append((lineno, "reference-full", m.group(0)))

            # Shortcut reference: `[text]` not followed by ( [ or :
            # Avoid double-counting things already matched by FULL_REF_RE.
            # We do this by blanking-out FULL_REF matches first.
            scrub2 = FULL_REF_RE.sub(lambda m: " " * len(m.group(0)), scrub)
            scrub2 = INLINE_LINK_RE.sub(lambda m: " " * len(m.group(0)), scrub2)
            for m in SHORTCUT_REF_RE.finditer(scrub2):
                # Heuristic: skip if the bracketed text looks like a footnote ref [^1]
                txt = m.group(1)
                if txt.startswith("^"):
                    continue
                ref_count += 1
                findings.append((lineno, "reference-shortcut", m.group(0)))

    findings.sort(key=lambda t: t[0])
    return findings, inline_count, ref_count


def main(argv: List[str]) -> int:
    if len(argv) != 2:
        print(f"usage: {argv[0]} <file.md>", file=sys.stderr)
        return 2

    path = argv[1]
    findings, inline_count, ref_count = find_links(path)

    total = inline_count + ref_count
    print(f"file: {path}")
    print(f"links found: {total} (inline={inline_count}, reference={ref_count})")

    if inline_count > 0 and ref_count > 0:
        print("MIX DETECTED: document uses both inline and reference link styles")
        for lineno, style, snippet in findings:
            print(f"  line {lineno} [{style}]: {snippet}")
        return 1

    print("OK: single link style (or no links)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
