#!/usr/bin/env python3
"""Detect non-canonical fenced code language tags in Markdown.

LLMs frequently emit the same language under multiple aliases within a single
document — e.g. ```py``` here, ```python``` two paragraphs later. Renderers
and syntax-highlighter configs that key off the tag string then disagree
about which highlighter to load, producing visually inconsistent docs.

This detector flags any fenced code block whose language tag is a known
alias of a canonical name. It DOES NOT flag unknown languages (use the
spelling detector for that). It DOES NOT require all blocks to use the
same language — only that each block uses the canonical spelling.

Exit codes:
  0 — clean
  1 — findings
  2 — usage error
"""
from __future__ import annotations

import re
import sys
from typing import Iterable

# alias -> canonical
ALIASES: dict[str, str] = {
    "py": "python",
    "py3": "python",
    "python3": "python",
    "js": "javascript",
    "node": "javascript",
    "ts": "typescript",
    "sh": "bash",
    "shell": "bash",
    "zsh": "bash",
    "yml": "yaml",
    "rb": "ruby",
    "kt": "kotlin",
    "rs": "rust",
    "golang": "go",
    "c++": "cpp",
    "cxx": "cpp",
    "objc": "objective-c",
    "cs": "csharp",
    "c#": "csharp",
    "ps": "powershell",
    "ps1": "powershell",
    "md": "markdown",
    "dockerfile": "docker",
    "html5": "html",
    "htm": "html",
}

FENCE_RE = re.compile(r"^(\s{0,3})(`{3,}|~{3,})\s*([^\s`]*)")


def find_fences(lines: Iterable[str]) -> list[tuple[int, str, str]]:
    """Return [(lineno, fence_marker, info_string_first_token)] for opening fences."""
    out: list[tuple[int, str, str]] = []
    in_fence = False
    open_marker = ""
    for i, line in enumerate(lines, start=1):
        m = FENCE_RE.match(line.rstrip("\n"))
        if not m:
            continue
        marker = m.group(2)
        info = m.group(3)
        if not in_fence:
            in_fence = True
            open_marker = marker[0]
            out.append((i, marker, info))
        else:
            # closing if same kind and at least as long
            if marker[0] == open_marker and len(marker) >= 3:
                in_fence = False
                open_marker = ""
    return out


def detect(path: str) -> int:
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.readlines()
    except OSError as e:
        print(f"error: cannot read {path}: {e}", file=sys.stderr)
        return 2

    fences = find_fences(lines)
    findings = 0
    for lineno, marker, info in fences:
        if not info:
            continue
        tag = info.lower()
        canonical = ALIASES.get(tag)
        if canonical and canonical != tag:
            print(
                f"{path}:{lineno}:1: non-canonical fence language tag "
                f"'{info}' — use '{canonical}'"
            )
            findings += 1

    if findings:
        print(f"\n{findings} finding(s)")
        return 1
    return 0


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: detect.py <markdown-file>", file=sys.stderr)
        return 2
    return detect(argv[1])


if __name__ == "__main__":
    sys.exit(main(sys.argv))
