#!/usr/bin/env python3
"""Detect fenced code blocks with no language tag.

Reads markdown on stdin and reports each opening fence (``` or ~~~) that
does not specify an info string (language tag). Most renderers and syntax
highlighters depend on the language tag to apply highlighting and to enable
copy buttons; LLM-generated markdown often omits it inconsistently.
"""
import re
import sys

FENCE = re.compile(r'^(\s*)(`{3,}|~{3,})\s*(.*)$')


def scan(text: str):
    findings = []
    in_fence = False
    open_char = ''
    open_run = 0
    for lineno, line in enumerate(text.splitlines(), 1):
        m = FENCE.match(line)
        if not m:
            continue
        indent, fence, info = m.group(1), m.group(2), m.group(3).strip()
        char = fence[0]
        run = len(fence)
        if not in_fence:
            in_fence = True
            open_char = char
            open_run = run
            if not info:
                findings.append((lineno, fence))
        else:
            # closing fence must match opener char and be at least as long
            if char == open_char and run >= open_run:
                in_fence = False
                open_char = ''
                open_run = 0
            # otherwise treat as content inside the open fence; skip
    return findings


def main() -> int:
    text = sys.stdin.read()
    findings = scan(text)
    if not findings:
        print("OK: every fenced code block has a language tag.")
        return 0
    print(f"FOUND {len(findings)} fence(s) missing a language tag:")
    for lineno, fence in findings:
        print(f"  line {lineno}: opening fence {fence!r} has no info string")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
