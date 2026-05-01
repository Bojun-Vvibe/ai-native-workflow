#!/usr/bin/env python3
"""Detect ``std::mem::transmute`` / ``mem::transmute`` /
``transmute_copy`` calls in Rust source.

See README.md for the full rationale. python3 stdlib only.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

SUPPRESS = "llm-allow:mem-transmute"
SCAN_SUFFIXES = (".rs", ".md", ".markdown")


def _strip_strings_and_comments(text: str) -> str:
    """Blank out Rust ``//`` and ``/* */`` comments and ``"..."`` /
    ``r#"..."#`` string literal bodies, preserving newlines so line
    numbers stay aligned.
    """
    out: list[str] = []
    i = 0
    n = len(text)
    block_depth = 0
    in_line_c = False
    in_str: str | None = None
    raw_hashes = 0
    while i < n:
        ch = text[i]
        nxt = text[i + 1] if i + 1 < n else ""
        if in_line_c:
            if ch == "\n":
                in_line_c = False
                out.append("\n")
            else:
                out.append(" ")
            i += 1
            continue
        if block_depth > 0:
            if ch == "/" and nxt == "*":
                block_depth += 1
                out.append("  ")
                i += 2
                continue
            if ch == "*" and nxt == "/":
                block_depth -= 1
                out.append("  ")
                i += 2
                continue
            out.append("\n" if ch == "\n" else " ")
            i += 1
            continue
        if in_str == '"':
            if ch == "\\" and i + 1 < n:
                out.append("  ")
                i += 2
                continue
            if ch == '"':
                out.append('"')
                in_str = None
                i += 1
                continue
            out.append("\n" if ch == "\n" else " ")
            i += 1
            continue
        if in_str == "R":
            if ch == '"':
                if text[i + 1 : i + 1 + raw_hashes] == "#" * raw_hashes:
                    out.append('"' + "#" * raw_hashes)
                    i += 1 + raw_hashes
                    in_str = None
                    raw_hashes = 0
                    continue
            out.append("\n" if ch == "\n" else " ")
            i += 1
            continue
        # Code mode.
        if ch == "/" and nxt == "/":
            in_line_c = True
            out.append("  ")
            i += 2
            continue
        if ch == "/" and nxt == "*":
            block_depth = 1
            out.append("  ")
            i += 2
            continue
        if ch == "r" and (nxt == '"' or nxt == "#"):
            j = i + 1
            hashes = 0
            while j < n and text[j] == "#":
                hashes += 1
                j += 1
            if j < n and text[j] == '"':
                out.append("r" + "#" * hashes + '"')
                i = j + 1
                in_str = "R"
                raw_hashes = hashes
                continue
        if ch == "'":
            # crude char-literal-vs-lifetime split; same as the
            # established detectors in this repo.
            if i + 2 < n and text[i + 2] == "'":
                out.append("' '")
                i += 3
                continue
            if (
                i + 3 < n
                and text[i + 1] == "\\"
                and text[i + 3] == "'"
            ):
                out.append("'  '")
                i += 4
                continue
            out.append(ch)
            i += 1
            continue
        if ch == '"':
            out.append('"')
            in_str = '"'
            i += 1
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def _line_of_offset(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _line_text(text: str, lineno: int) -> str:
    lines = text.splitlines()
    if 1 <= lineno <= len(lines):
        return lines[lineno - 1]
    return ""


# Match transmute / transmute_copy with optional `std::mem::` /
# `mem::` / `core::mem::` prefix. Negative lookbehind on word char so
# `something_transmute(...)` is not caught.
RE_TRANSMUTE = re.compile(
    r"(?<![A-Za-z0-9_])"
    r"(?:(?:std|core)\s*::\s*)?(?:mem\s*::\s*)?"
    r"(transmute(?:_copy)?)\s*(?:::\s*<[^>]*>)?\s*\("
)


def scan_text_rust(path: Path, text: str) -> list[tuple[Path, int, str, str]]:
    findings: list[tuple[Path, int, str, str]] = []
    cleaned = _strip_strings_and_comments(text)
    for m in RE_TRANSMUTE.finditer(cleaned):
        # Disambiguate the bare `transmute` call: only flag if the
        # token is preceded somewhere on the same line/file by either
        # an `unsafe` block, an `unsafe fn`, or a `mem::`/`std::mem::`
        # prefix in the match itself. We check the matched span first.
        matched = cleaned[m.start():m.end()]
        has_path = ("mem::" in matched) or ("std::" in matched) or ("core::" in matched)
        # Decide the kind label.
        which = m.group(1)  # transmute or transmute_copy
        kind = "mem-transmute-copy-call" if which == "transmute_copy" else "mem-transmute-call"

        if not has_path:
            # Bare `transmute(...)`: only treat as the std fn when the
            # surrounding scope is `unsafe` or `unsafe fn`. Otherwise
            # it could be a user-defined helper and we skip.
            # Look back ~400 chars for `unsafe` or `unsafe fn`.
            window_start = max(0, m.start() - 400)
            prior = cleaned[window_start:m.start()]
            if not re.search(r"\bunsafe\b", prior):
                continue

        lineno = _line_of_offset(cleaned, m.start())
        line_str = _line_text(text, lineno)
        if (
            SUPPRESS in line_str
            or SUPPRESS in _line_text(text, max(1, lineno - 1))
        ):
            continue
        findings.append((path, lineno, kind, line_str.rstrip()))
    return findings


RE_FENCE_OPEN = re.compile(
    r"(?m)^([`~]{3,})[ \t]*([A-Za-z0-9_+\-./]*)[^\n]*$"
)


def _md_extract_rust(text: str) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    pos = 0
    while True:
        m = RE_FENCE_OPEN.search(text, pos)
        if not m:
            return out
        fence = m.group(1)
        lang = (m.group(2) or "").lower()
        body_start = m.end() + 1
        close_re = re.compile(
            r"(?m)^" + fence[0] + "{" + str(len(fence)) + r",}[ \t]*$"
        )
        cm = close_re.search(text, body_start)
        if not cm:
            return out
        if lang in ("rust", "rs"):
            out.append((body_start, cm.start()))
        pos = cm.end()


def scan_text_md(path: Path, text: str) -> list[tuple[Path, int, str, str]]:
    findings: list[tuple[Path, int, str, str]] = []
    for body_start, body_end in _md_extract_rust(text):
        body = text[body_start:body_end]
        sub = scan_text_rust(path, body)
        offset_lines = text.count("\n", 0, body_start)
        for p, ln, kind, line in sub:
            findings.append((p, ln + offset_lines, kind, line))
    return findings


def scan_file(path: Path) -> list[tuple[Path, int, str, str]]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    suf = path.suffix.lower()
    if suf in (".md", ".markdown"):
        return scan_text_md(path, text)
    return scan_text_rust(path, text)


def iter_paths(args: list[str]) -> list[Path]:
    out: list[Path] = []
    for a in args:
        p = Path(a)
        if p.is_file():
            out.append(p)
        elif p.is_dir():
            for sub in sorted(p.rglob("*")):
                if sub.is_file() and sub.suffix.lower() in SCAN_SUFFIXES:
                    out.append(sub)
    return out


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: detect.py <file_or_dir> [...]", file=sys.stderr)
        return 2
    findings: list[tuple[Path, int, str, str]] = []
    for path in iter_paths(argv[1:]):
        findings.extend(scan_file(path))
    for path, lineno, kind, line in findings:
        print(f"{path}:{lineno}: {kind}: {line}")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
