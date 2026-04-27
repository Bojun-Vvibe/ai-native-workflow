#!/usr/bin/env python3
"""Detect probable typos in fenced code language tags.

LLMs sometimes hallucinate slightly misspelled language tags in Markdown
fenced code info-strings -- e.g. ```pyhton```, ```javscript```, ```tyepscript```,
```bahs```. These are not aliases (so the canonicalization detector misses
them) and not blank (so the missing-tag detector misses them). They look
plausible, but every syntax highlighter falls back to "no highlighting"
because the tag matches no known language.

This detector flags any opening fence whose info-string first token is
within edit-distance 1 of a known canonical language tag, but is NOT
itself in the known set (canonical or alias). That keeps false positives
low: `python` is canonical (ignored), `py` is a known alias (ignored),
`pyhton` is one transposition away from `python` and not known (flagged).

It is code-fence-aware: nested fences (e.g. a ```` ``` ```` inside a
````` ```` ````` block) are tracked so info-strings inside an open fence
are NOT re-scanned as new openings.

Exit codes:
  0 — clean
  1 — findings
  2 — usage error
"""
from __future__ import annotations

import re
import sys
from typing import Iterable

# Known good tags (canonical + common aliases). Anything within edit-distance
# 1 of a member here, that is NOT itself a member, is flagged as a typo.
KNOWN: frozenset[str] = frozenset({
    # canonical
    "python", "javascript", "typescript", "bash", "yaml", "json", "ruby",
    "kotlin", "rust", "go", "cpp", "csharp", "powershell", "markdown",
    "docker", "html", "css", "sql", "java", "swift", "scala", "perl",
    "lua", "php", "haskell", "elixir", "erlang", "clojure", "dart",
    "objective-c", "groovy", "r", "julia", "ocaml", "fsharp", "zig",
    "nim", "crystal", "vim", "diff", "ini", "toml", "xml", "text",
    "plaintext", "console", "shell-session", "make", "cmake", "nginx",
    "apache", "graphql", "protobuf",
    # common aliases (also accepted as-is)
    "py", "py3", "python3", "js", "node", "ts", "sh", "shell", "zsh",
    "yml", "rb", "kt", "rs", "golang", "c++", "cxx", "objc", "cs", "c#",
    "ps", "ps1", "md", "dockerfile", "html5", "htm", "txt",
})

FENCE_RE = re.compile(r"^(\s{0,3})(`{3,}|~{3,})\s*([^\s`]*)")


def find_opening_fences(lines: Iterable[str]) -> list[tuple[int, str]]:
    """Return [(lineno, info_first_token)] for OPENING fences only.

    Tracks open/close state so info-strings inside a fenced block are not
    treated as new openings.
    """
    out: list[tuple[int, str]] = []
    in_fence = False
    open_marker_char = ""
    open_marker_len = 0
    for i, raw in enumerate(lines, start=1):
        line = raw.rstrip("\n")
        m = FENCE_RE.match(line)
        if not m:
            continue
        marker = m.group(2)
        info = m.group(3)
        if not in_fence:
            in_fence = True
            open_marker_char = marker[0]
            open_marker_len = len(marker)
            out.append((i, info))
        else:
            # closing requires same marker char, length >= opening, no info
            if (
                marker[0] == open_marker_char
                and len(marker) >= open_marker_len
                and info == ""
            ):
                in_fence = False
                open_marker_char = ""
                open_marker_len = 0
    return out


def edit_distance_le_1(a: str, b: str) -> bool:
    """True iff Damerau-Levenshtein distance(a, b) <= 1.

    Counts a single adjacent transposition as ONE edit, so that
    ``pyhton`` vs ``python`` (one swap) is detected as a typo.
    Stdlib only.
    """
    if a == b:
        return True
    la, lb = len(a), len(b)
    if abs(la - lb) > 1:
        return False
    if la == lb:
        # walk and find first mismatch
        diffs = [i for i in range(la) if a[i] != b[i]]
        if len(diffs) == 1:
            return True
        if len(diffs) == 2:
            i, j = diffs
            # adjacent swap?
            if j == i + 1 and a[i] == b[j] and a[j] == b[i]:
                return True
        return False
    # length differs by 1: one insertion/deletion
    if la > lb:
        a, b = b, a
        la, lb = lb, la
    i = j = 0
    skipped = False
    while i < la and j < lb:
        if a[i] == b[j]:
            i += 1
            j += 1
        else:
            if skipped:
                return False
            skipped = True
            j += 1
    return True


def nearest_known(tag: str) -> str | None:
    for k in KNOWN:
        if abs(len(k) - len(tag)) > 1:
            continue
        if edit_distance_le_1(tag, k):
            return k
    return None


def detect(path: str) -> int:
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.readlines()
    except OSError as e:
        print(f"error: cannot read {path}: {e}", file=sys.stderr)
        return 2

    findings = 0
    for lineno, info in find_opening_fences(lines):
        if not info:
            continue
        tag = info.lower()
        if tag in KNOWN:
            continue
        suggestion = nearest_known(tag)
        if suggestion is None:
            # unknown but not close to anything known -> not a typo, skip
            continue
        print(
            f"{path}:{lineno}:1: probable language-tag typo "
            f"'{info}' — did you mean '{suggestion}'?"
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
