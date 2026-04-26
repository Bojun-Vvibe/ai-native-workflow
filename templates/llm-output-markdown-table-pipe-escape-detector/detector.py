#!/usr/bin/env python3
"""Detect unescaped `|` characters inside markdown table cells.

A markdown pipe table uses `|` as the column separator. To put a literal
pipe inside a cell you must escape it as `\\|`. LLMs frequently forget this
when emitting tables that contain shell pipelines, regex alternations, or
type unions like `int | str`. The result is a row that silently splits into
extra columns, often invisibly misaligned in the rendered view.

Heuristic: a pipe is "unescaped" if it is not preceded by a backslash and
is not at a column boundary. We approximate column boundaries by the
header row's pipe count: any data row whose pipe count exceeds the header
has at least one stray pipe.

Usage:
    python3 detector.py <file>

Exits non-zero if any rows are inconsistent.
"""
import sys
import re


PIPE = re.compile(r"(?<!\\)\|")


def is_separator(line: str) -> bool:
    s = line.strip().strip("|").strip()
    if not s:
        return False
    parts = [p.strip() for p in s.split("|")]
    return all(re.fullmatch(r":?-{3,}:?", p) for p in parts)


def count_pipes(line: str) -> int:
    return len(PIPE.findall(line.rstrip("\n")))


def scan(path: str) -> int:
    with open(path, "r", encoding="utf-8") as fh:
        lines = fh.readlines()

    hits = 0
    i = 0
    while i < len(lines):
        line = lines[i]
        # Header candidate: contains a pipe and next line is a separator
        if "|" in line and i + 1 < len(lines) and is_separator(lines[i + 1]):
            header_pipes = count_pipes(line)
            sep_pipes = count_pipes(lines[i + 1])
            expected = max(header_pipes, sep_pipes)
            i += 2
            while i < len(lines) and "|" in lines[i] and lines[i].strip():
                row_pipes = count_pipes(lines[i])
                if row_pipes != expected:
                    diff = row_pipes - expected
                    print(
                        f"{path}:{i+1}: table row has {row_pipes} unescaped pipes, "
                        f"header has {expected} (diff {diff:+d}) -- likely missing \\| escape"
                    )
                    print(f"    row: {lines[i].rstrip()!r}")
                    hits += 1
                i += 1
        else:
            i += 1
    return hits


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: detector.py <file> [<file>...]", file=sys.stderr)
        return 2
    total = 0
    for p in argv[1:]:
        total += scan(p)
    if total:
        print(f"\nFAIL: {total} table row(s) with pipe-count mismatch")
        return 1
    print("OK: all markdown table rows have consistent pipe counts")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
