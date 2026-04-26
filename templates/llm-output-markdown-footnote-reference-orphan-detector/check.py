#!/usr/bin/env python3
"""
llm-output-markdown-footnote-reference-orphan-detector

Detects orphan markdown footnotes:
  - References like [^id] used in body but with no matching definition `[^id]: text`
  - Definitions `[^id]: text` that are never referenced
  - Duplicate definitions for the same footnote id

Reads markdown from stdin or a file path passed as argv[1].
Exit code: 0 if clean, 1 if any orphans/duplicates found.
"""
from __future__ import annotations

import re
import sys
from collections import Counter

# A reference is [^id] NOT immediately followed by ':' (which would make it a definition).
# id is letters/digits/_/- per common GFM-ish conventions.
REF_RE = re.compile(r"(?<!\\)\[\^([A-Za-z0-9_-]+)\](?!:)")
# A definition starts at the beginning of a line: [^id]: ...
DEF_RE = re.compile(r"^\s{0,3}\[\^([A-Za-z0-9_-]+)\]:\s", re.MULTILINE)


def strip_fenced_code(text: str) -> str:
    """Remove fenced code blocks so footnote-like syntax inside code is ignored."""
    out_lines = []
    in_fence = False
    fence_marker = ""
    for line in text.splitlines():
        stripped = line.lstrip()
        if not in_fence and (stripped.startswith("```") or stripped.startswith("~~~")):
            in_fence = True
            fence_marker = stripped[:3]
            continue
        if in_fence and stripped.startswith(fence_marker):
            in_fence = False
            continue
        if not in_fence:
            out_lines.append(line)
    return "\n".join(out_lines)


def analyze(text: str) -> dict:
    cleaned = strip_fenced_code(text)
    refs = REF_RE.findall(cleaned)
    defs = DEF_RE.findall(cleaned)

    ref_set = set(refs)
    def_counts = Counter(defs)
    def_set = set(def_counts)

    refs_without_defs = sorted(ref_set - def_set)
    defs_without_refs = sorted(def_set - ref_set)
    duplicate_defs = sorted([d for d, c in def_counts.items() if c > 1])

    return {
        "refs_without_defs": refs_without_defs,
        "defs_without_refs": defs_without_refs,
        "duplicate_defs": duplicate_defs,
        "ref_count": len(refs),
        "def_count": len(defs),
    }


def main() -> int:
    if len(sys.argv) > 1:
        with open(sys.argv[1], "r", encoding="utf-8") as fh:
            text = fh.read()
    else:
        text = sys.stdin.read()

    result = analyze(text)
    issues = (
        len(result["refs_without_defs"])
        + len(result["defs_without_refs"])
        + len(result["duplicate_defs"])
    )

    print(f"footnote refs found:       {result['ref_count']}")
    print(f"footnote defs found:       {result['def_count']}")
    print(f"refs without definition:   {result['refs_without_defs']}")
    print(f"defs without reference:    {result['defs_without_refs']}")
    print(f"duplicate definitions:     {result['duplicate_defs']}")
    print(f"status: {'FAIL' if issues else 'OK'} ({issues} issue(s))")
    return 1 if issues else 0


if __name__ == "__main__":
    sys.exit(main())
