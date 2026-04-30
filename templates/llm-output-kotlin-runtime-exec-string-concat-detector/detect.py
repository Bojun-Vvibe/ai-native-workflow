#!/usr/bin/env python3
"""Detect Kotlin Runtime.exec / ProcessBuilder calls built from interpolated
or concatenated strings (CWE-78 OS command injection)."""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

# A "tainted string literal" = a "..." or """...""" that contains either:
#   - $ident or ${...}   (Kotlin string template), or
#   - is part of a "..." + expr  /  expr + "..."  concatenation chain.
# We approximate by scanning each call-site line (and the previous line for
# trailing-`+` continuations) for these markers.

_TEMPLATE = re.compile(r'"(?:[^"\\]|\\.)*\$(?:\w+|\{[^}]+\})[^"]*"')
_CONCAT = re.compile(r'"[^"]*"\s*\+|\+\s*"[^"]*"')
_TRIPLE_TEMPLATE = re.compile(r'"""[\s\S]*?\$(?:\w+|\{[^}]+\})[\s\S]*?"""')

RULES = [
    # rule_id, regex matching the call site (must contain the sink invocation)
    ("runtime-exec-string-interp",
     re.compile(r'Runtime\s*\.\s*getRuntime\s*\(\s*\)\s*\.\s*exec\s*\(\s*(?!arrayOf)')),
    ("runtime-exec-array-interp",
     re.compile(r'Runtime\s*\.\s*getRuntime\s*\(\s*\)\s*\.\s*exec\s*\(\s*arrayOf\s*\(')),
    ("process-builder-string-interp",
     re.compile(r'\bProcessBuilder\s*\(\s*(?!listOf|arrayOf|mutableListOf)')),
    ("process-builder-list-interp",
     re.compile(r'\bProcessBuilder\s*\(\s*(?:listOf|mutableListOf|arrayOf)\s*\(')),
    ("process-builder-command-set",
     re.compile(r'\.\s*command\s*\(')),
]


def _is_tainted(snippet: str) -> bool:
    if _TEMPLATE.search(snippet) or _TRIPLE_TEMPLATE.search(snippet):
        return True
    if _CONCAT.search(snippet):
        return True
    return False


def scan_file(path: Path) -> list[tuple[Path, int, str, str]]:
    findings: list[tuple[Path, int, str, str]] = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return findings
    lines = text.splitlines()
    for idx, line in enumerate(lines, start=1):
        if "// detector:ignore" in line:
            continue
        # Build a small window: current line + up to 2 trailing-continuation lines
        window = line
        j = idx
        while j < len(lines) and lines[j - 1].rstrip().endswith(("+", "(", ",")):
            window += "\n" + lines[j]
            j += 1
            if j - idx > 4:
                break
        for rule_id, sink_re in RULES:
            if not sink_re.search(line):
                continue
            if not _is_tainted(window):
                continue
            findings.append((path, idx, rule_id, line.strip()))
            break
    return findings


def walk(root: Path):
    if root.is_file():
        yield root
        return
    for dirpath, _, filenames in os.walk(root):
        for name in filenames:
            if name.endswith((".kt", ".kts")):
                yield Path(dirpath) / name


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: detect.py <path>", file=sys.stderr)
        return 2
    root = Path(argv[1])
    if not root.exists():
        print(f"no such path: {root}", file=sys.stderr)
        return 2
    all_findings: list[tuple[Path, int, str, str]] = []
    for f in walk(root):
        all_findings.extend(scan_file(f))
    for path, line_no, rule, snippet in all_findings:
        print(f"{path}:{line_no}:{rule}: {snippet}")
    return 1 if all_findings else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
