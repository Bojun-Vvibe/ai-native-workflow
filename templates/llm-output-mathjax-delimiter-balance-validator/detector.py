#!/usr/bin/env python3
"""Validate balance of MathJax / KaTeX math delimiters in Markdown.

Stdlib only. See README.md for rules.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import List, Tuple

FENCE_RE = re.compile(r"^(\s*)(`{3,}|~{3,})")
INLINE_CODE_RE = re.compile(r"(`+)([^`].*?)\1")


def strip_fenced_blocks(lines: List[str]) -> List[str]:
    """Replace lines inside fenced code blocks with empty strings (preserve numbering)."""
    out: List[str] = []
    in_fence = False
    fence_marker = ""
    for line in lines:
        m = FENCE_RE.match(line)
        if not in_fence and m:
            in_fence = True
            fence_marker = m.group(2)[0]
            out.append("")
            continue
        if in_fence:
            # Closing fence: same marker char, length >= opener.
            stripped = line.lstrip()
            if stripped.startswith(fence_marker * 3) and set(stripped.rstrip()) == {fence_marker}:
                in_fence = False
            out.append("")
            continue
        out.append(line)
    return out


def strip_inline_code(line: str) -> str:
    """Remove inline code spans from a line."""
    return INLINE_CODE_RE.sub(lambda m: " " * len(m.group(0)), line)


def count_unescaped(text: str, target: str) -> List[int]:
    """Return positions of unescaped occurrences of `target` in `text`."""
    positions: List[int] = []
    i = 0
    n = len(text)
    tlen = len(target)
    while i <= n - tlen:
        if text[i:i + tlen] == target:
            # Count preceding backslashes; even => not escaped.
            bs = 0
            j = i - 1
            while j >= 0 and text[j] == "\\":
                bs += 1
                j -= 1
            if bs % 2 == 0:
                positions.append(i)
                i += tlen
                continue
        i += 1
    return positions


def split_paragraphs(lines: List[str]) -> List[Tuple[int, str]]:
    """Yield (start_lineno_1based, paragraph_text) for blank-line-separated paragraphs."""
    paras: List[Tuple[int, str]] = []
    cur: List[str] = []
    cur_start = 0
    for idx, line in enumerate(lines, start=1):
        if line.strip() == "":
            if cur:
                paras.append((cur_start, "\n".join(cur)))
                cur = []
        else:
            if not cur:
                cur_start = idx
            cur.append(line)
    if cur:
        paras.append((cur_start, "\n".join(cur)))
    return paras


def analyze(path: Path) -> List[str]:
    raw = path.read_text(encoding="utf-8")
    lines = raw.splitlines()
    stripped_lines = strip_fenced_blocks(lines)
    # Strip inline code per line.
    stripped_lines = [strip_inline_code(l) for l in stripped_lines]

    findings: List[str] = []

    # Per-paragraph: inline $ balance.
    paras = split_paragraphs(stripped_lines)
    for start, text in paras:
        # Remove $$ first so they don't pollute single-$ count.
        dd_positions = count_unescaped(text, "$$")
        # Replace $$ pairs with placeholder of same length.
        masked = list(text)
        for p in dd_positions:
            masked[p] = " "
            masked[p + 1] = " "
        masked_text = "".join(masked)
        single = count_unescaped(masked_text, "$")
        if len(single) % 2 != 0:
            findings.append(
                f"{path}:{start}: odd-inline-dollar: paragraph starting at line "
                f"{start} has {len(single)} unescaped '$' (must be even)"
            )

    # Whole document: $$ balance.
    full_text = "\n".join(stripped_lines)
    dd_total = count_unescaped(full_text, "$$")
    if len(dd_total) % 2 != 0:
        findings.append(
            f"{path}:1: odd-display-dollar: document has {len(dd_total)} "
            "unescaped '$$' (must be even)"
        )

    # Bracket-style balance.
    open_paren = count_unescaped(full_text.replace("\\\\", "  "), "\\(")
    close_paren = count_unescaped(full_text.replace("\\\\", "  "), "\\)")
    if len(open_paren) != len(close_paren):
        findings.append(
            f"{path}:1: paren-bracket-imbalance: '\\(' count={len(open_paren)} "
            f"vs '\\)' count={len(close_paren)}"
        )

    open_bracket = count_unescaped(full_text.replace("\\\\", "  "), "\\[")
    close_bracket = count_unescaped(full_text.replace("\\\\", "  "), "\\]")
    if len(open_bracket) != len(close_bracket):
        findings.append(
            f"{path}:1: square-bracket-imbalance: '\\[' count={len(open_bracket)} "
            f"vs '\\]' count={len(close_bracket)}"
        )

    return findings


def main(argv: List[str]) -> int:
    if len(argv) < 2:
        print("usage: detector.py <file.md> [<file.md> ...]", file=sys.stderr)
        return 2
    all_findings: List[str] = []
    for arg in argv[1:]:
        p = Path(arg)
        if not p.is_file():
            print(f"error: not a file: {arg}", file=sys.stderr)
            return 2
        all_findings.extend(analyze(p))
    for f in all_findings:
        print(f)
    return 1 if all_findings else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
