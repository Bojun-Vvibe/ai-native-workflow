#!/usr/bin/env python3
"""Detect bare URLs in Markdown that are not wrapped as CommonMark autolinks.

A "bare URL" here is an `http://` or `https://` URL that appears in the
prose with neither:

  - autolink wrapping  `<https://example.com>`
  - inline link form   `[label](https://example.com)`
  - reference link     `[label][1]` ... `[1]: https://example.com`

CommonMark only renders bare URLs as clickable links under the GFM
"autolink literal" extension. In strict CommonMark renderers (and many
RAG pipelines / static-site generators) a bare URL stays as plain text
and breaks navigability. The fix is to wrap the URL in `<...>` so it
becomes an autolink across all renderers.

Stdlib only. The detector is fence- and inline-code-aware (URLs in
fenced code blocks or inline `code spans` are intentionally ignored).

Usage:
    python3 detect.py FILE [FILE ...]

Exit codes:
    0  clean (no bare URLs)
    1  one or more bare URLs found
    2  usage / IO error
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

FENCE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
INLINE_CODE_RE = re.compile(r"`+[^`\n]*`+")
URL_RE = re.compile(r"https?://[^\s<>\[\]()`'\"]+")
# Stop URL at common trailing punctuation that is almost never part of a URL.
TRAILING_PUNCT = ".,;:!?)"


def trim_trailing_punct(url: str) -> str:
    while url and url[-1] in TRAILING_PUNCT:
        url = url[:-1]
    return url


def is_inside_autolink(line: str, start: int) -> bool:
    # An autolink looks like `<https://...>`. Check the char before is `<`
    # and there is a `>` after the URL with no intervening whitespace.
    if start == 0 or line[start - 1] != "<":
        return False
    end = start
    while end < len(line) and line[end] not in " \t<>":
        end += 1
    return end < len(line) and line[end] == ">"


def is_inside_inline_link(line: str, start: int) -> bool:
    # An inline link destination looks like `](https://...`. The char
    # immediately before the URL must be `(` and that `(` must be
    # immediately preceded by `]`.
    if start < 2:
        return False
    if line[start - 1] != "(":
        return False
    # Find the `]` that opens the destination — allow no whitespace between.
    return line[start - 2] == "]"


def is_inside_reference_definition(line: str) -> bool:
    # A reference link definition: `[label]: https://example.com`
    return bool(re.match(r"^ {0,3}\[[^\]]+\]:\s+\S", line))


def scan(path: Path) -> list[str]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"{path}: cannot read: {exc}", file=sys.stderr)
        return ["__io__"]

    lines = text.splitlines()
    findings: list[str] = []

    in_fence = False
    fence_char = ""

    for idx, line in enumerate(lines, start=1):
        m = FENCE_RE.match(line)
        if m:
            ch = m.group(1)[0]
            if not in_fence:
                in_fence = True
                fence_char = ch
            elif ch == fence_char:
                in_fence = False
                fence_char = ""
            continue
        if in_fence:
            continue
        if is_inside_reference_definition(line):
            continue

        scrubbed = INLINE_CODE_RE.sub(lambda m: " " * len(m.group(0)), line)

        for match in URL_RE.finditer(scrubbed):
            url = trim_trailing_punct(match.group(0))
            if not url:
                continue
            start = match.start()
            if is_inside_autolink(line, start):
                continue
            if is_inside_inline_link(line, start):
                continue
            findings.append(
                f"{path}:{idx}:{start + 1}: bare URL {url!r} not wrapped as autolink (use <{url}> or [text]({url}))"
            )

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
