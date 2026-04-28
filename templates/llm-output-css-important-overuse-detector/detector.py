#!/usr/bin/env python3
"""Detect overuse of `!important` in CSS.

LLMs frequently reach for `!important` to "win" specificity battles when
generating CSS suggestions. A few uses are defensible (utility resets,
print stylesheets, third-party widget overrides). Sprinkling them
throughout a stylesheet defeats the cascade and makes future overrides
require ever-louder `!important` chains.

This sniffer scans `.css`, `.scss`, `.less` files (anything you pass on
the CLI) and reports:

  - Every `!important` occurrence (line + declaration).
  - A summary count and a per-file density (per 100 declarations).
  - A flag when density exceeds a threshold (default 5%).

Usage:
  python3 detector.py [--threshold N] <file.css> [...]

Exit code is the total number of `!important` occurrences (capped 255).
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

IMPORTANT_RE = re.compile(r"!\s*important\b", re.IGNORECASE)
DECL_RE = re.compile(r"[A-Za-z\-]+\s*:\s*[^;{}]+;")


def strip_comments(src: str) -> str:
    # Remove /* ... */ comments (CSS only — works for SCSS block comments too).
    out = []
    i, n = 0, len(src)
    while i < n:
        if src[i : i + 2] == "/*":
            j = src.find("*/", i + 2)
            if j == -1:
                break
            i = j + 2
        else:
            out.append(src[i])
            i += 1
    return "".join(out)


def scan(path: Path) -> tuple[list[tuple[int, str]], int]:
    text = path.read_text(encoding="utf-8", errors="replace")
    stripped = strip_comments(text)
    decl_count = len(DECL_RE.findall(stripped))
    findings: list[tuple[int, str]] = []
    in_block_comment = False
    for i, raw in enumerate(text.splitlines(), 1):
        line = raw
        if in_block_comment:
            if "*/" in line:
                line = line.split("*/", 1)[1]
                in_block_comment = False
            else:
                continue
        if "/*" in line:
            before, _, rest = line.partition("/*")
            if "*/" in rest:
                line = before + rest.split("*/", 1)[1]
            else:
                line = before
                in_block_comment = True
        # Strip // line comments (SCSS/LESS)
        if "//" in line:
            line = line.split("//", 1)[0]
        if IMPORTANT_RE.search(line):
            findings.append((i, raw.strip()))
    return findings, decl_count


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--threshold", type=float, default=5.0,
                    help="density %% above which density is flagged (default 5.0)")
    ap.add_argument("files", nargs="+")
    args = ap.parse_args(argv[1:])

    grand = 0
    for f in args.files:
        p = Path(f)
        if not p.exists():
            print(f"{f}: not found", file=sys.stderr)
            continue
        findings, decls = scan(p)
        for line_no, text in findings:
            print(f"{p}:{line_no}: !important: {text}")
        if decls:
            density = (len(findings) / decls) * 100.0
        else:
            density = 0.0
        flag = " OVER-THRESHOLD" if density > args.threshold else ""
        print(f"{p}: {len(findings)} !important / {decls} decls "
              f"({density:.1f}%){flag}")
        grand += len(findings)
    print(f"findings: {grand}")
    return min(grand, 255)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
