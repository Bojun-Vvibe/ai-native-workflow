#!/usr/bin/env python3
"""Detect Markdown reference-link definitions that are defined but never used.

Stdlib only. Code-fence and inline-code aware.

Usage:
    python3 detect.py FILE [FILE ...]

Exit codes:
    0  no unused definitions
    1  unused definitions found
    2  usage / IO error
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# Reference definition: optional 0-3 space indent, [label]: url ...
DEF_RE = re.compile(r"^ {0,3}\[([^\]\n]+)\]:\s*\S+")
# Full reference link/image: [text][label] or ![alt][label]
FULL_REF_RE = re.compile(r"!?\[(?:[^\[\]]|\\.)*\]\[([^\[\]]+)\]")
# Collapsed reference link/image: [text][] or ![alt][]
COLLAPSED_REF_RE = re.compile(r"!?\[((?:[^\[\]]|\\.)+)\]\[\]")
# Shortcut reference (just [label]) — only when not followed by ( or [ or :
SHORTCUT_REF_RE = re.compile(r"!?\[((?:[^\[\]]|\\.)+)\](?![\(\[:])")

FENCE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
INLINE_CODE_RE = re.compile(r"`+[^`\n]*`+")


def normalize_label(label: str) -> str:
    return " ".join(label.lower().split())


def strip_inline_code(line: str) -> str:
    return INLINE_CODE_RE.sub("", line)


def scan(path: Path) -> list[str]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"{path}: cannot read: {exc}", file=sys.stderr)
        return ["__io__"]

    lines = text.splitlines()

    # Pass 1: collect definitions (label -> first defining line number).
    definitions: dict[str, int] = {}
    in_fence = False
    fence_marker = ""
    for idx, line in enumerate(lines, start=1):
        m = FENCE_RE.match(line)
        if m:
            marker = m.group(1)[0]
            if not in_fence:
                in_fence = True
                fence_marker = marker
            elif marker == fence_marker:
                in_fence = False
                fence_marker = ""
            continue
        if in_fence:
            continue
        dm = DEF_RE.match(line)
        if dm:
            label = normalize_label(dm.group(1))
            definitions.setdefault(label, idx)

    # Pass 2: collect used labels.
    used: set[str] = set()
    in_fence = False
    fence_marker = ""
    for line in lines:
        m = FENCE_RE.match(line)
        if m:
            marker = m.group(1)[0]
            if not in_fence:
                in_fence = True
                fence_marker = marker
            elif marker == fence_marker:
                in_fence = False
                fence_marker = ""
            continue
        if in_fence:
            continue
        if DEF_RE.match(line):
            continue  # definition line is not a "use"
        scrubbed = strip_inline_code(line)
        for m in FULL_REF_RE.finditer(scrubbed):
            used.add(normalize_label(m.group(1)))
        for m in COLLAPSED_REF_RE.finditer(scrubbed):
            used.add(normalize_label(m.group(1)))
        # Shortcut form: only count as a use if a definition exists for it,
        # to avoid treating every `[bracketed thing]` as a reference.
        for m in SHORTCUT_REF_RE.finditer(scrubbed):
            label = normalize_label(m.group(1))
            if label in definitions:
                used.add(label)

    findings: list[str] = []
    for label, lineno in definitions.items():
        if label not in used:
            findings.append(
                f"{path}:{lineno}: unused reference definition '[{label}]:'"
            )
    findings.sort()
    return findings


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: detect.py FILE [FILE ...]", file=sys.stderr)
        return 2
    rc = 0
    for arg in argv[1:]:
        results = scan(Path(arg))
        if results == ["__io__"]:
            rc = max(rc, 2)
            continue
        for line in results:
            print(line)
        if results:
            rc = max(rc, 1)
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv))
