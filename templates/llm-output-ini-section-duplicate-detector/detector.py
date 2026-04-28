#!/usr/bin/env python3
"""Detect duplicated [section] headers in INI-style files.

Most INI parsers either:
  - silently merge the sections (Python's configparser by default
    raises DuplicateSectionError, but many lenient parsers just merge),
  - or keep only the last occurrence, dropping all earlier keys.

LLMs that emit large INI configs (tox.ini, setup.cfg, alembic.ini,
systemd unit overrides) commonly repeat a section header by accident,
especially when stitching answers from multiple sources.

This detector reports each duplicated section with the lines on which
it appeared. Pure stdlib. Code-fence aware so it can be pointed at a
markdown blob containing INI snippets.
"""
from __future__ import annotations

import sys
from pathlib import Path


def detect(text: str):
    seen: dict[str, list[int]] = {}
    in_fence = False
    for lineno, raw in enumerate(text.splitlines(), start=1):
        stripped = raw.strip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if not stripped or stripped.startswith(("#", ";")):
            continue
        if stripped.startswith("[") and stripped.endswith("]") and len(stripped) >= 2:
            name = stripped[1:-1].strip()
            if not name:
                continue
            seen.setdefault(name, []).append(lineno)
    findings = [
        {"section": name, "lines": lines}
        for name, lines in seen.items()
        if len(lines) > 1
    ]
    findings.sort(key=lambda f: f["lines"][0])
    return findings


def main(argv):
    if len(argv) != 2:
        print("usage: detector.py <file>", file=sys.stderr)
        return 2
    text = Path(argv[1]).read_text(encoding="utf-8")
    findings = detect(text)
    if not findings:
        print("OK: no duplicate sections")
        return 0
    print(f"FOUND {len(findings)} duplicated section(s):")
    for f in findings:
        line_list = ", ".join(str(n) for n in f["lines"])
        print(f"  [{f['section']}] appears on lines {line_list}")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
