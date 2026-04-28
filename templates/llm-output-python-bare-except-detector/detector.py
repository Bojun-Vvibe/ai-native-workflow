#!/usr/bin/env python3
"""Detect bare/over-broad except clauses in Python code.

Stdlib only. Code-fence aware for Markdown input. Always exits 0.
"""

from __future__ import annotations

import re
import sys
from typing import Iterator, Tuple, List


BARE_EXCEPT_RE = re.compile(r"^(\s*)except\s*:")
BASE_EXCEPT_RE = re.compile(r"^(\s*)except\s+BaseException\s*(?:as\s+\w+)?\s*:")
GENERIC_EXCEPT_RE = re.compile(r"^(\s*)except\s+Exception\s*(?:as\s+\w+)?\s*:")
FENCE_RE = re.compile(r"^(\s*)(`{3,}|~{3,})\s*([A-Za-z0-9_+\-]*)\s*$")
PYTHON_LANGS = {"python", "python3", "py"}


def _iter_python_lines(text: str, is_markdown: bool) -> Iterator[Tuple[int, str]]:
    if not is_markdown:
        for i, line in enumerate(text.splitlines(), start=1):
            yield i, line
        return

    in_fence = False
    fence_char = ""
    fence_len = 0
    fence_lang = ""
    for i, line in enumerate(text.splitlines(), start=1):
        m = FENCE_RE.match(line)
        if m and not in_fence:
            fence_char = m.group(2)[0]
            fence_len = len(m.group(2))
            fence_lang = m.group(3).lower()
            in_fence = True
            continue
        if in_fence and m:
            if m.group(2)[0] == fence_char and len(m.group(2)) >= fence_len and not m.group(3):
                in_fence = False
                fence_lang = ""
                continue
        if in_fence and fence_lang in PYTHON_LANGS:
            yield i, line


def _looks_like_markdown(path: str, text: str) -> bool:
    if path.lower().endswith((".md", ".markdown")):
        return True
    return bool(re.search(r"(?m)^\s*```", text))


def _strip_inline_comment(line: str) -> str:
    # naive: cut at first # not preceded by quote — good enough since we only
    # check structural form of `except` lines, not strings.
    out = []
    in_s = False
    in_d = False
    i = 0
    while i < len(line):
        ch = line[i]
        if ch == "'" and not in_d:
            in_s = not in_s
        elif ch == '"' and not in_s:
            in_d = not in_d
        elif ch == "#" and not in_s and not in_d:
            break
        out.append(ch)
        i += 1
    return "".join(out).rstrip()


def _next_nonblank_code(lines: List[str], idx: int) -> Tuple[int, str] | None:
    """Return (line_index, line_content) for the next non-blank, non-comment line."""
    j = idx + 1
    while j < len(lines):
        s = lines[j].strip()
        if not s or s.startswith("#"):
            j += 1
            continue
        return j, lines[j]
    return None


def scan(path: str, text: str) -> int:
    is_md = _looks_like_markdown(path, text)
    raw_lines = text.splitlines()
    selected = list(_iter_python_lines(text, is_md))
    selected_index = {lineno: line for lineno, line in selected}

    findings = 0
    sorted_linenos = sorted(selected_index.keys())
    pos_in_selected = {ln: i for i, ln in enumerate(sorted_linenos)}

    for lineno in sorted_linenos:
        line = selected_index[lineno]
        cleaned = _strip_inline_comment(line)

        if BARE_EXCEPT_RE.match(cleaned):
            print(f"{path}:{lineno}: PYEXC001: bare except clause | {line.strip()}")
            findings += 1
            continue
        if BASE_EXCEPT_RE.match(cleaned):
            print(
                f"{path}:{lineno}: PYEXC002: except BaseException catches "
                f"KeyboardInterrupt/SystemExit | {line.strip()}"
            )
            findings += 1
            continue
        if GENERIC_EXCEPT_RE.match(cleaned):
            # look for next non-blank line WITHIN the same selection that is
            # `pass` and indented deeper than the except clause
            indent = len(line) - len(line.lstrip())
            pos = pos_in_selected[lineno]
            nxt_pass = False
            for k in range(pos + 1, len(sorted_linenos)):
                nxt_lineno = sorted_linenos[k]
                nxt_line = selected_index[nxt_lineno]
                stripped = nxt_line.strip()
                if not stripped or stripped.startswith("#"):
                    continue
                nxt_indent = len(nxt_line) - len(nxt_line.lstrip())
                if nxt_indent <= indent:
                    break  # left the except body
                if stripped == "pass":
                    nxt_pass = True
                break
            if nxt_pass:
                print(
                    f"{path}:{lineno}: PYEXC003: except Exception followed by "
                    f"silent pass | {line.strip()}"
                )
                findings += 1

    print(f"# findings: {findings}")
    return findings


def _read(path: str) -> str:
    if path == "-":
        return sys.stdin.read()
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: detector.py <path|-> [more paths...]", file=sys.stderr)
        print("# findings: 0")
        return 0
    for p in argv[1:]:
        display = p if p != "-" else "<stdin>"
        try:
            text = _read(p)
        except OSError as e:
            print(f"{display}: ERROR: {e}", file=sys.stderr)
            continue
        scan(display, text)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
