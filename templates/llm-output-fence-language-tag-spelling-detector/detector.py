#!/usr/bin/env python3
"""Detect likely-misspelled language tags on fenced code blocks.

Many LLMs emit fences like ```pyhton or ```javscript or ```yml
where a near-canonical tag exists. This detector flags tags that:
  - are not in a known allowlist, AND
  - have a small edit distance (<=2) to a known tag

Exit code 0 = clean, 1 = findings.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

KNOWN_TAGS = {
    "python", "py", "javascript", "js", "typescript", "ts",
    "bash", "sh", "shell", "zsh", "fish",
    "json", "yaml", "yml", "toml", "ini", "xml", "html", "css", "scss",
    "markdown", "md", "rust", "go", "java", "kotlin", "swift",
    "c", "cpp", "csharp", "ruby", "php", "perl", "lua", "r",
    "sql", "graphql", "dockerfile", "makefile", "diff", "patch",
    "text", "plaintext", "console", "tsx", "jsx", "vue", "svelte",
    "haskell", "scala", "elixir", "clojure", "ocaml", "fsharp",
    "protobuf", "thrift", "hcl", "terraform", "nginx", "apache",
}

FENCE_RE = re.compile(r"^(\s*)(```+|~~~+)([^\s`]*)\s*$")


def edit_distance(a: str, b: str, cap: int = 3) -> int:
    """Bounded Levenshtein. Returns >cap if exceeds cap."""
    if a == b:
        return 0
    if abs(len(a) - len(b)) > cap:
        return cap + 1
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i] + [0] * len(b)
        row_min = cur[0]
        for j, cb in enumerate(b, 1):
            cost = 0 if ca == cb else 1
            cur[j] = min(
                prev[j] + 1,
                cur[j - 1] + 1,
                prev[j - 1] + cost,
            )
            if cur[j] < row_min:
                row_min = cur[j]
        if row_min > cap:
            return cap + 1
        prev = cur
    return prev[-1]


def find_suggestion(tag: str) -> str | None:
    low = tag.lower()
    if low in KNOWN_TAGS:
        return None
    best = None
    best_d = 99
    for k in KNOWN_TAGS:
        d = edit_distance(low, k, cap=2)
        if d <= 2 and d < best_d:
            best = k
            best_d = d
    return best


def scan(path: Path) -> list[tuple[int, str, str]]:
    findings = []
    in_fence = False
    fence_marker = ""
    for lineno, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
        m = FENCE_RE.match(line)
        if not m:
            continue
        marker = m.group(2)
        tag = m.group(3)
        if not in_fence:
            in_fence = True
            fence_marker = marker[0]
            if tag:
                sug = find_suggestion(tag)
                if sug is not None:
                    findings.append((lineno, tag, sug))
        else:
            if marker.startswith(fence_marker):
                in_fence = False
                fence_marker = ""
    return findings


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: detector.py FILE [FILE ...]", file=sys.stderr)
        return 2
    total = 0
    for arg in argv[1:]:
        p = Path(arg)
        if not p.is_file():
            print(f"skip (not a file): {arg}", file=sys.stderr)
            continue
        for lineno, tag, sug in scan(p):
            print(f"{p}:{lineno}: misspelled fence tag {tag!r} -> did you mean {sug!r}?")
            total += 1
    if total:
        print(f"\n{total} finding(s).", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
