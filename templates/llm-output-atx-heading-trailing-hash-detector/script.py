#!/usr/bin/env python3
"""Detect ATX headings with trailing closing hashes.

ATX headings of the form `## Title ##` are valid CommonMark but considered
stylistically inconsistent in most house styles. This script reads markdown
on stdin and reports each heading line that ends with one or more `#`
characters after the title text. It ignores fenced code blocks.
"""
import re
import sys

HEADING = re.compile(r'^(#{1,6})\s+(.*?)\s+(#+)\s*$')
OPEN_HEADING = re.compile(r'^(#{1,6})\s+(.*\S)\s*$')
FENCE = re.compile(r'^\s*(`{3,}|~{3,})')


def scan(text: str):
    in_fence = False
    findings = []
    for lineno, line in enumerate(text.splitlines(), 1):
        if FENCE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        m = HEADING.match(line)
        if m:
            level = len(m.group(1))
            findings.append((lineno, level, m.group(2), m.group(3)))
    return findings


def main() -> int:
    text = sys.stdin.read()
    findings = scan(text)
    if not findings:
        print("OK: no ATX headings with trailing hashes found.")
        return 0
    print(f"FOUND {len(findings)} heading(s) with trailing hashes:")
    for lineno, level, title, tail in findings:
        print(f"  line {lineno}: level={level} title={title!r} trailing={tail!r}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
