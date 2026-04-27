#!/usr/bin/env python3
"""Detect inconsistent or malformed blockquote attribution lines.

Stdlib only. See README.md for rules.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import List, Tuple

# Attribution patterns. Order matters: em-dash first so it wins over hyphen.
EM_DASH = "\u2014"
ATTR_PATTERNS = [
    ("em-dash", re.compile(r"^\s*" + EM_DASH + r"\s*(.*)$")),
    ("double-hyphen", re.compile(r"^\s*--\s*(.+)$")),
    ("single-hyphen", re.compile(r"^\s*-\s+([A-Z].*)$")),
]


def classify_attribution(text: str) -> Tuple[str, str] | None:
    """Return (style, author) if the line looks like an attribution, else None."""
    for style, pat in ATTR_PATTERNS:
        m = pat.match(text)
        if m:
            return style, m.group(1).strip()
    return None


def strip_quote_marker(line: str) -> str:
    """Remove leading '>' markers and the single optional space."""
    s = line
    while s.startswith(">"):
        s = s[1:]
        if s.startswith(" "):
            s = s[1:]
    return s


def find_blockquote_blocks(lines: List[str]) -> List[Tuple[int, int]]:
    """Return list of (start_idx, end_idx_exclusive) for each blockquote block."""
    blocks: List[Tuple[int, int]] = []
    i = 0
    n = len(lines)
    while i < n:
        if lines[i].lstrip().startswith(">"):
            start = i
            while i < n and lines[i].lstrip().startswith(">"):
                i += 1
            blocks.append((start, i))
        else:
            i += 1
    return blocks


def analyze(path: Path) -> List[str]:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    findings: List[str] = []

    blocks = find_blockquote_blocks(lines)
    block_styles: List[Tuple[int, str]] = []  # (block_start_lineno_1based, style)

    for start, end in blocks:
        # Inspect last non-empty content line of the block.
        last_content = None
        last_idx = None
        for j in range(end - 1, start - 1, -1):
            stripped = strip_quote_marker(lines[j]).strip()
            if stripped:
                last_content = stripped
                last_idx = j
                break
            # Treat lone '>' or '> ' as empty.
        if last_content is None:
            continue

        attr = classify_attribution(last_content)
        if attr is None:
            continue
        style, author = attr
        if not author:
            findings.append(
                f"{path}:{last_idx + 1}: orphan-attribution: blockquote ends with "
                f"{style!r} but no author text follows"
            )
            continue
        block_styles.append((start + 1, style))

        # Check next non-blank line after block: attribution outside blockquote.
        k = end
        while k < len(lines) and not lines[k].strip():
            k += 1
        if k < len(lines):
            next_line = lines[k]
            outside = classify_attribution(next_line)
            if outside is not None and outside[1]:
                findings.append(
                    f"{path}:{k + 1}: attribution-outside-blockquote: "
                    f"line {k + 1} ({outside[0]}) appears after a blockquote "
                    "but is not itself blockquoted"
                )

    # Also scan: any blockquote followed (skipping blanks) by an attribution
    # line that isn't quoted. This catches blocks with no internal attribution.
    for start, end in blocks:
        k = end
        while k < len(lines) and not lines[k].strip():
            k += 1
        if k >= len(lines):
            continue
        next_line = lines[k]
        outside = classify_attribution(next_line)
        if outside is None or not outside[1]:
            continue
        # Skip if we already reported it above.
        marker = (
            f"{path}:{k + 1}: attribution-outside-blockquote:"
        )
        if any(f.startswith(marker) for f in findings):
            continue
        findings.append(
            f"{path}:{k + 1}: attribution-outside-blockquote: "
            f"line {k + 1} ({outside[0]}) appears after a blockquote "
            "but is not itself blockquoted"
        )

    # Mixed-style detection across the document.
    styles_seen = {s for _, s in block_styles}
    if len(styles_seen) >= 2:
        # Pick majority style; report the rest.
        counts: dict[str, int] = {}
        for _, s in block_styles:
            counts[s] = counts.get(s, 0) + 1
        majority = max(counts.items(), key=lambda kv: kv[1])[0]
        for lineno, s in block_styles:
            if s != majority:
                findings.append(
                    f"{path}:{lineno}: mixed-attribution-style: blockquote uses "
                    f"{s!r} but document majority is {majority!r}"
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
