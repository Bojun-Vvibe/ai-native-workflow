#!/usr/bin/env python3
"""Detect non-canonical marker spacing in nested Markdown blockquotes.

Canonical form: '> > > content' — single space between every '>' marker
and exactly one space before the content. Flags:

  - '>>...'         no space between adjacent markers
  - '>  >'          extra (>=2) spaces between markers
  - '>>x' or '> >x' no space before content (when ≥2 markers present)
  - '> > x' is OK   (canonical)
  - '> x' single-level is NOT checked (no nesting)

Lines inside fenced code blocks are ignored.
Stdlib only. Exit 0 if clean, 1 if findings, 2 on usage error.
"""
from __future__ import annotations

import re
import sys

FENCE_RE = re.compile(r"^\s*(```+|~~~+)")
# Capture leading whitespace, then the blockquote prefix region (chars from
# the set '>' and ' ' and '\t'), then the rest.
PREFIX_RE = re.compile(r"^(?P<lead>[ \t]{0,3})(?P<prefix>>[>\s]*)(?P<rest>.*)$")


def analyze_prefix(prefix: str, rest: str) -> str | None:
    """Return a finding description if prefix is non-canonical for nested
    blockquotes, else None. `prefix` starts with '>' and contains only '>'
    or whitespace. `rest` is the content after the prefix.
    """
    # Count markers
    marker_count = prefix.count(">")
    if marker_count < 2:
        return None  # not nested; out of scope

    # Walk the prefix and verify canonical pattern: '>' (' >')* ' '
    # Build the canonical string and compare.
    canonical = "> " * (marker_count - 1) + ">"
    # The prefix as written may or may not end with a space; we expect exactly
    # one space between prefix and rest. So full canonical is canonical + ' '.
    # But the regex already greedily consumed trailing whitespace into prefix.
    # Reconstruct: trailing whitespace in prefix should be exactly one space
    # (and rest should not start with whitespace) OR rest is empty.
    # Easiest: normalize prefix by collapsing runs of whitespace to ' ' and
    # check both shape and the join with rest.

    # Detect '>>' (adjacent markers with no space)
    if ">>" in prefix:
        return "adjacent '>>' markers without separating space"

    # Split into tokens of '>' separated by whitespace runs
    tokens = re.findall(r">|[ \t]+", prefix)
    # Validate alternation: > ws > ws > [ws]
    # Expected pattern: > (ws >)+ optional trailing ws
    expected_marker = True
    last_ws = ""
    for i, tok in enumerate(tokens):
        if expected_marker:
            if tok != ">":
                return f"unexpected token {tok!r} in blockquote prefix"
            expected_marker = False
        else:
            # whitespace token
            if tok != " ":
                return f"non-single-space ({len(tok)} chars) between blockquote markers"
            last_ws = tok
            expected_marker = True

    # After tokens, prefix may or may not end in whitespace.
    prefix_ends_with_space = prefix.endswith(" ") or prefix.endswith("\t")

    if rest == "":
        # Empty quoted line is fine regardless of trailing space.
        return None

    if not prefix_ends_with_space:
        # No space between final '>' and content -> '>>x' style or '> >x'
        return "missing space between final '>' and content"

    # prefix ends with whitespace; check it is exactly one space.
    # Find trailing whitespace run length.
    trailing = len(prefix) - len(prefix.rstrip(" \t"))
    if trailing > 1:
        return f"{trailing} spaces between final '>' and content (expected 1)"
    if "\t" in prefix[-trailing:]:
        return "tab between final '>' and content (expected single space)"

    return None


def scan(path: str) -> int:
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except OSError as exc:
        print(f"error: cannot read {path}: {exc}", file=sys.stderr)
        return 2

    findings: list[str] = []
    in_fence = False
    fence_marker = ""

    for lineno, raw in enumerate(lines, start=1):
        line = raw.rstrip("\n")
        fm = FENCE_RE.match(line)
        if fm:
            tok = fm.group(1)
            if not in_fence:
                in_fence = True
                fence_marker = tok[0]
            elif tok[0] == fence_marker:
                in_fence = False
                fence_marker = ""
            continue
        if in_fence:
            continue

        m = PREFIX_RE.match(line)
        if not m:
            continue
        prefix = m.group("prefix")
        rest = m.group("rest")
        problem = analyze_prefix(prefix, rest)
        if problem:
            findings.append(f"{path}:{lineno}: {problem}: {line!r}")

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
