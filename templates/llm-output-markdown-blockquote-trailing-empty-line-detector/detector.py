#!/usr/bin/env python3
"""
llm-output-markdown-blockquote-trailing-empty-line-detector

Detects blockquote groups in markdown that end with one or more
"empty" blockquote lines — lines whose content (after stripping the
leading `>` markers and any indentation) is whitespace-only.

Failure mode caught:
    > A real quote.
    > Another sentence.
    >
    >

The blockquote technically renders, but most renderers either drop
the trailing empty `>` lines silently or render an awkward extra
paragraph break. LLMs frequently emit this because they "close" a
quote with an empty `>` instead of just letting the blockquote end.

Code-fence aware: lines inside ``` / ~~~ fenced code blocks are
ignored entirely, so a literal `>` shown as code does not flag.

Stdlib only. Exit code 0 always; findings printed to stdout, one per
line, in `path:line: message` form. A summary line is printed last.
"""
from __future__ import annotations

import sys


def _strip_bq_prefix(line: str) -> str | None:
    """Return the content after the blockquote marker(s), or None.

    A blockquote line per CommonMark may have up to 3 leading spaces,
    a `>` marker, and an optional single space. Nested blockquotes
    repeat the `>`. We strip *all* leading `>` markers (and the
    intervening single optional space) and return the remainder.
    """
    i = 0
    n = len(line)
    # Up to 3 leading spaces.
    spaces = 0
    while i < n and line[i] == " " and spaces < 3:
        i += 1
        spaces += 1
    if i >= n or line[i] != ">":
        return None
    # Strip one or more `>` markers, each optionally followed by a single space.
    while i < n and line[i] == ">":
        i += 1
        if i < n and line[i] == " ":
            i += 1
    return line[i:]


def _is_fence_line(stripped: str) -> str | None:
    """Return the fence char ('`' or '~') if the line opens/closes a fence."""
    if stripped.startswith("```"):
        rest = stripped[3:]
        if "`" not in rest:
            return "`"
    if stripped.startswith("~~~"):
        rest = stripped[3:]
        if "~" not in rest:
            return "~"
    return None


def scan(path: str, text: str) -> list[tuple[int, str]]:
    findings: list[tuple[int, str]] = []
    lines = text.splitlines()

    in_fence = False
    fence_char: str | None = None

    # A blockquote group is a maximal run of consecutive blockquote
    # lines (no intervening blank, non-blockquote line). For each
    # group, we check if the trailing line(s) are empty-after-marker.
    group_lines: list[tuple[int, str]] = []  # (line_no_1based, content_after_marker)

    def flush_group() -> None:
        if not group_lines:
            return
        # Walk from the end; collect trailing empty-content lines.
        trailing_empty: list[int] = []
        for ln, content in reversed(group_lines):
            if content.strip() == "":
                trailing_empty.append(ln)
            else:
                break
        if trailing_empty:
            trailing_empty.reverse()
            count = len(trailing_empty)
            first_ln = trailing_empty[0]
            msg = (
                f"blockquote ends with {count} trailing empty `>` "
                f"line(s); strip them or terminate the blockquote "
                f"with a blank line instead"
            )
            findings.append((first_ln, msg))
        group_lines.clear()

    for idx, raw in enumerate(lines, start=1):
        stripped = raw.strip()

        # Fence toggle handling first; fence lines themselves are
        # never considered blockquote content.
        fc = _is_fence_line(stripped.lstrip())
        if in_fence:
            if fc is not None and fc == fence_char:
                in_fence = False
                fence_char = None
            # Any line inside a fence flushes any open group.
            flush_group()
            continue
        else:
            if fc is not None:
                in_fence = True
                fence_char = fc
                flush_group()
                continue

        content = _strip_bq_prefix(raw)
        if content is None:
            # Not a blockquote line: this terminates any open group.
            flush_group()
            continue
        group_lines.append((idx, content))

    # EOF flush.
    flush_group()

    return findings


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(f"usage: {argv[0]} <markdown-file> [<markdown-file> ...]",
              file=sys.stderr)
        return 2
    total = 0
    for path in argv[1:]:
        try:
            with open(path, "r", encoding="utf-8") as fh:
                text = fh.read()
        except OSError as exc:
            print(f"{path}: error: {exc}", file=sys.stderr)
            continue
        findings = scan(path, text)
        for ln, msg in findings:
            print(f"{path}:{ln}: {msg}")
        total += len(findings)
    print(f"summary: {total} finding(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
