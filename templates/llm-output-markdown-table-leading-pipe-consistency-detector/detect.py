#!/usr/bin/env python3
"""Detect inconsistent leading-pipe style across rows of a single markdown
GFM table.

GitHub-flavored markdown tables allow rows to optionally begin (and end) with
a pipe character. Within a single table, rows should use the same convention.
Mixing leading-pipe and no-leading-pipe rows in the same table is a common
LLM output defect that often signals the table was assembled from inconsistent
fragments.

Exit 1 if any single table contains rows with both styles. Code/fenced regions
are excluded.

Usage: detect.py FILE
"""
import re
import sys


def strip_fences(lines):
    out = []
    in_fence = False
    for line in lines:
        s = line.lstrip()
        if s.startswith('```') or s.startswith('~~~'):
            in_fence = not in_fence
            out.append(None)  # sentinel: not table content
            continue
        if in_fence:
            out.append(None)
            continue
        out.append(line)
    return out


def is_separator_row(stripped):
    # GFM separator: cells of dashes, optional colons, separated by pipes
    if not re.search(r'-{3,}', stripped):
        return False
    # remove leading/trailing pipes for the cell check
    body = stripped.strip('|').strip()
    cells = [c.strip() for c in body.split('|')]
    if not cells:
        return False
    for c in cells:
        if not re.fullmatch(r':?-{3,}:?', c):
            return False
    return True


def looks_like_table_row(line):
    if line is None:
        return False
    return '|' in line


def main(path):
    with open(path, encoding='utf-8') as f:
        raw = f.read()
    lines = strip_fences(raw.splitlines())

    # Walk and collect contiguous table blocks. A table block is a run of
    # consecutive lines that all contain '|', containing at least one
    # separator row.
    findings = 0
    table_index = 0
    i = 0
    n = len(lines)
    while i < n:
        if looks_like_table_row(lines[i]):
            j = i
            while j < n and looks_like_table_row(lines[j]):
                j += 1
            block = list(range(i, j))
            block_lines = [lines[k].rstrip() for k in block]
            has_sep = any(is_separator_row(bl.strip()) for bl in block_lines)
            if has_sep and len(block_lines) >= 2:
                table_index += 1
                lead_pipe = []
                no_lead_pipe = []
                for offset, bl in enumerate(block_lines):
                    stripped = bl.lstrip()
                    if not stripped:
                        continue
                    lineno = block[offset] + 1
                    if stripped.startswith('|'):
                        lead_pipe.append(lineno)
                    else:
                        no_lead_pipe.append(lineno)
                if lead_pipe and no_lead_pipe:
                    print(f"{path}: table #{table_index} has inconsistent leading-pipe style")
                    for ln in lead_pipe:
                        print(f"  {path}:{ln}: leading-pipe row")
                        findings += 1
                    for ln in no_lead_pipe:
                        print(f"  {path}:{ln}: no-leading-pipe row")
                        findings += 1
            i = j
        else:
            i += 1

    if findings:
        print(f"total findings: {findings}")
        return 1
    return 0


if __name__ == '__main__':
    if len(sys.argv) != 2:
        print("usage: detect.py FILE", file=sys.stderr)
        sys.exit(2)
    sys.exit(main(sys.argv[1]))
