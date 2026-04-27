#!/usr/bin/env python3
"""Detect fenced code block opening lines whose info string contains a
duplicated or repeated language token.

LLMs frequently emit fences like:

    ```python python
    ```py python
    ```python language=python
    ```python (python)

These render as one ambiguous info string. Most renderers either keep
only the first token or display the entire string verbatim above the
block; either way the output is sloppy and fragile (syntax highlighting
gates on the first token).

Heuristic: split the info string on whitespace into tokens. After
normalizing each token (lowercase, strip common decorators like
`language=`, surrounding `()`/`{}`/`[]`, and a `lang-` prefix), flag
the fence if the same canonical language token appears more than once,
OR if a known alias of the first token appears later (e.g. python/py,
javascript/js, typescript/ts, shell/sh/bash, yaml/yml, markdown/md).

Code-fence aware: only the *opening* fence line is examined; the body
of any fenced block is skipped until the matching closing fence.

Exit codes:
  0 = no findings
  1 = findings printed to stdout
  2 = usage error
"""
from __future__ import annotations

import re
import sys

OPEN_FENCE_RE = re.compile(r"^(\s{0,3})(`{3,}|~{3,})(.*)$")

# Aliases that should canonicalize to the same language.
ALIAS_GROUPS = [
    {"python", "py", "python3"},
    {"javascript", "js", "node"},
    {"typescript", "ts"},
    {"shell", "sh", "bash", "zsh"},
    {"yaml", "yml"},
    {"markdown", "md"},
    {"c++", "cpp", "cxx"},
    {"c#", "csharp", "cs"},
    {"ruby", "rb"},
    {"rust", "rs"},
    {"golang", "go"},
    {"text", "plain", "plaintext", "txt"},
    {"html", "htm"},
]

ALIAS_MAP: dict[str, str] = {}
for group in ALIAS_GROUPS:
    canon = sorted(group)[0]
    for member in group:
        ALIAS_MAP[member] = canon


DECORATOR_RE = re.compile(r"^(?:lang(?:uage)?[=:])(.+)$", re.IGNORECASE)


def normalize_token(tok: str) -> str:
    t = tok.strip().lower()
    # Strip surrounding brackets/parens.
    while t and t[0] in "([{<" and t[-1] in ")]}>":
        t = t[1:-1].strip()
    # Strip language= / lang= / language: prefix.
    m = DECORATOR_RE.match(t)
    if m:
        t = m.group(1).strip()
    # Strip a leading 'lang-' (e.g. 'lang-python').
    if t.startswith("lang-"):
        t = t[5:]
    # Strip trailing punctuation that isn't part of an identifier.
    t = t.rstrip(",;:")
    return t


def canonicalize(tok: str) -> str:
    n = normalize_token(tok)
    return ALIAS_MAP.get(n, n)


def analyze_info_string(info: str) -> list[str]:
    """Return a list of duplicate-canonical tokens found in info.

    Returns the canonical name(s) that repeat, in first-seen order.
    Empty list = no duplicates.
    """
    raw_tokens = info.strip().split()
    canon_seen: dict[str, int] = {}
    duplicates: list[str] = []
    for raw in raw_tokens:
        c = canonicalize(raw)
        if not c:
            continue
        canon_seen[c] = canon_seen.get(c, 0) + 1
        if canon_seen[c] == 2:
            duplicates.append(c)
    return duplicates


def scan(text: str):
    findings = []
    in_fence = False
    fence_marker = ""
    for i, raw in enumerate(text.splitlines(), 1):
        m = OPEN_FENCE_RE.match(raw)
        if not in_fence and m:
            indent, marker, info = m.group(1), m.group(2), m.group(3)
            in_fence = True
            fence_marker = marker[0] * len(marker)
            dups = analyze_info_string(info)
            if dups:
                findings.append(
                    (
                        i,
                        f"duplicate language token(s) in info string: {dups}",
                        raw,
                    )
                )
            continue
        if in_fence:
            # Closing fence: same character, length >= opening, no info.
            stripped = raw.strip()
            if stripped and set(stripped) == {fence_marker[0]} and len(stripped) >= len(fence_marker):
                in_fence = False
                fence_marker = ""
            continue
    return findings


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(f"usage: {argv[0]} <file.md>", file=sys.stderr)
        return 2
    path = argv[1]
    try:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
    except OSError as exc:
        print(f"error reading {path}: {exc}", file=sys.stderr)
        return 2
    findings = scan(text)
    for line_no, msg, raw in findings:
        print(f"{path}:{line_no}: {msg}: {raw.rstrip()}")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
