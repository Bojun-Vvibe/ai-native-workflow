#!/usr/bin/env python3
"""Detect tab characters used for indentation in YAML output.

YAML spec forbids tabs for indentation. LLMs sometimes emit tabs, especially
when prompted to "format as YAML" inside a chat that uses tab-rendered code.
The result parses inconsistently across loaders: PyYAML rejects it, some
permissive parsers silently treat tabs as a single space, etc.

Usage:
    python3 detector.py < input.yaml

Reads YAML from stdin, prints findings (one per line) of the form:
    line=<N> col=<C> kind=<indent-tab|inline-tab> snippet=<...>

Exit code: 0 always (advisory). Count of findings printed at end on stderr.
"""
from __future__ import annotations

import sys
from typing import Iterable


def find_tabs(lines: Iterable[str]) -> list[tuple[int, int, str, str]]:
    findings: list[tuple[int, int, str, str]] = []
    for lineno, raw in enumerate(lines, start=1):
        line = raw.rstrip("\n")
        if "\t" not in line:
            continue
        # Classify: leading-indent tab vs inline tab.
        # Walk leading whitespace.
        leading_tab_col = -1
        for i, ch in enumerate(line):
            if ch == "\t":
                leading_tab_col = i + 1  # 1-indexed
                break
            if ch == " ":
                continue
            break
        if leading_tab_col != -1:
            findings.append(
                (lineno, leading_tab_col, "indent-tab", line[:60])
            )
            # Don't double-report inline tabs on same line; indent is the worst.
            continue
        # Otherwise, every tab on the line is "inline".
        for i, ch in enumerate(line):
            if ch == "\t":
                findings.append(
                    (lineno, i + 1, "inline-tab", line[:60])
                )
    return findings


def main() -> int:
    data = sys.stdin.read()
    findings = find_tabs(data.splitlines(keepends=False))
    for lineno, col, kind, snippet in findings:
        # Make snippet safe for single-line print.
        safe = snippet.replace("\t", "\\t")
        print(f"line={lineno} col={col} kind={kind} snippet={safe!r}")
    print(f"total_findings={len(findings)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
