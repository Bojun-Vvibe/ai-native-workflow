#!/usr/bin/env python3
"""
llm-output-markdown-emphasis-unmatched-asterisk-detector

Per-line detector for unmatched `*` emphasis runs in markdown.

It counts asterisk *runs* (consecutive `*` of length 1 or 2) on each
non-fenced line, after stripping inline code spans (`...`), escaped
`\\*`, and list-item leading markers (`* item`, `- item`, `+ item`).
If the parity-weighted run count for a line is odd, the line has at
least one unmatched emphasis or strong delimiter.

Why a line-scoped check rather than a whole-document parser:
CommonMark emphasis cannot cross paragraph boundaries, so any real
emphasis pair must close on the same paragraph. We approximate at
the line level (the strictest, lowest-false-positive granularity)
and only flag lines with clearly-odd asterisk parity.

Code-fence aware:
  * Lines inside ``` / ~~~ fences are skipped.
  * Inline code spans `like this` are stripped before counting.

Stdlib only. Output is `path:line: message`. A `summary: N
finding(s)` line closes the run. Exit code is always 0.
"""
from __future__ import annotations

import re
import sys


_FENCE_RE = re.compile(r"^\s{0,3}(`{3,}|~{3,})")
_INLINE_CODE_RE = re.compile(r"`+[^`\n]*`+")
_LIST_LEADER_RE = re.compile(r"^(\s{0,3})([*+\-])\s+")


def _strip_escapes_and_code(line: str) -> str:
    # Remove escaped asterisks first so they don't enter run counting.
    line = line.replace("\\*", "")
    # Remove balanced inline code spans.
    line = _INLINE_CODE_RE.sub("", line)
    return line


def _strip_list_leader(line: str) -> str:
    # A leading "* " (or "- ", "+ ") is a list marker, not emphasis.
    m = _LIST_LEADER_RE.match(line)
    if m and m.group(2) == "*":
        return line[: m.start(2)] + line[m.end(2) :]
    return line


def _asterisk_runs(line: str) -> list[int]:
    runs: list[int] = []
    i = 0
    n = len(line)
    while i < n:
        if line[i] == "*":
            j = i
            while j < n and line[j] == "*":
                j += 1
            runs.append(j - i)
            i = j
        else:
            i += 1
    return runs


def _line_unmatched(line: str) -> int:
    """Return parity-weighted asterisk count for emphasis purposes.

    A run of length 1 contributes 1 (one `*` delimiter).
    A run of length 2 contributes 2 (one `**` delimiter pair-side).
    A run of length 3 contributes 3 (combined `***`).
    Higher runs are reduced modulo behavior of CommonMark — we treat
    any run as contributing its length, then check overall parity.
    Odd total = unmatched emphasis somewhere on the line.
    """
    runs = _asterisk_runs(line)
    return sum(runs) % 2


def scan(path: str, text: str) -> list[tuple[int, str]]:
    findings: list[tuple[int, str]] = []
    in_fence = False
    fence_marker = ""
    for idx, raw in enumerate(text.splitlines(), start=1):
        m = _FENCE_RE.match(raw)
        if m:
            marker_char = m.group(1)[0]
            if not in_fence:
                in_fence = True
                fence_marker = marker_char
                continue
            elif marker_char == fence_marker:
                in_fence = False
                fence_marker = ""
                continue
        if in_fence:
            continue

        cleaned = _strip_list_leader(raw)
        cleaned = _strip_escapes_and_code(cleaned)
        if "*" not in cleaned:
            continue
        if _line_unmatched(cleaned) == 1:
            runs = _asterisk_runs(cleaned)
            findings.append(
                (
                    idx,
                    f"unmatched `*` emphasis run on line "
                    f"(asterisk runs: {runs}, total parity odd)",
                )
            )
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
