#!/usr/bin/env python3
"""Detect ``std::str::from_utf8_unchecked`` (and the equivalent
``String::from_utf8_unchecked``) used inside an ``unsafe`` block on
input that the surrounding code has not just validated.

Background
----------

``std::str::from_utf8_unchecked(bytes)`` and
``String::from_utf8_unchecked(vec)`` are ``unsafe`` constructors whose
safety contract is *"the caller has verified that bytes are valid
UTF-8"*. Constructing a ``&str`` from non-UTF-8 bytes is **immediate
undefined behavior**, not a Result. LLM-generated code very commonly:

* swaps ``from_utf8`` for ``from_utf8_unchecked`` "to avoid the Result"
  without any validation;
* wraps a raw socket / file / stdin / FFI buffer in ``unsafe { ... }``
  and hands it directly to ``from_utf8_unchecked``.

Both shapes are flagged here.

What this flags
---------------

A finding is emitted whenever ``std::str::from_utf8_unchecked(...)``
or ``String::from_utf8_unchecked(...)`` (or the bare
``from_utf8_unchecked(...)`` after a ``use``) is called and **all** of
the following hold:

* the call is lexically inside an ``unsafe { ... }`` block (only
  ``unsafe`` calls are reachable in real code);
* the same scope does **not** contain a preceding call to
  ``std::str::from_utf8`` / ``str::from_utf8`` /
  ``String::from_utf8`` / ``simdutf8::*::from_utf8`` /
  ``.is_ascii()`` / ``.utf8_chunks()`` / a ``debug_assert`` or
  ``assert`` mentioning ``from_utf8`` (these heuristics are the
  evidence-of-validation the safety contract asks for).

Suppression marker (per-line, in a comment): ``// llm-allow:from-utf8-unchecked``.

Rust-aware token handling: ``//`` line comments, ``/* */`` block
comments (with depth tracking, since Rust block comments nest), and
``"..."`` and ``r#"..."#`` (raw) string literal bodies are blanked.

The detector also extracts fenced ``rust`` code from Markdown.

Usage::

    python3 detect.py <file_or_dir> [...]

Exit ``1`` if any findings, ``0`` otherwise. python3 stdlib only.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

SUPPRESS = "llm-allow:from-utf8-unchecked"
SCAN_SUFFIXES = (".rs", ".md", ".markdown")

VALIDATION_HINTS = (
    "std::str::from_utf8",
    "str::from_utf8",
    "String::from_utf8",
    "simdutf8::basic::from_utf8",
    "simdutf8::compat::from_utf8",
    ".is_ascii()",
    ".utf8_chunks()",
    "from_utf8(",  # catches `let s = from_utf8(...)` after `use`
)

ASSERT_HINTS = (
    "assert!",
    "debug_assert!",
    "assert_eq!",
    "debug_assert_eq!",
)


def _strip_strings_and_comments(text: str) -> str:
    out: list[str] = []
    i = 0
    n = len(text)
    block_depth = 0  # Rust block comments nest.
    in_line_c = False
    in_str: str | None = None  # '"' for normal, 'R' for raw
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
            # Raw string: closes at "<n hashes>
            if ch == '"':
                # Look for the matching number of hashes.
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
        # Raw string: r"..." or r#"..."# or r##"..."##
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
        # Char literal — single quotes can be lifetimes too. Approximate:
        # a char literal is `'.'` or `'\..'`. A lifetime is `'name`.
        if ch == "'":
            # Look ahead.
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
            # Otherwise treat as code (lifetime or unrecognized).
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


def _find_matching(text: str, open_idx: int, opener: str, closer: str) -> int:
    depth = 0
    n = len(text)
    i = open_idx
    while i < n:
        c = text[i]
        if c == opener:
            depth += 1
        elif c == closer:
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


def _find_enclosing_scope_start(cleaned: str, idx: int) -> int:
    """Walk backward from ``idx`` and return the offset of the nearest
    enclosing ``{`` (the byte after it) that has unmatched depth at
    ``idx``. Falls back to 0.
    """
    depth = 0
    i = idx - 1
    while i >= 0:
        c = cleaned[i]
        if c == "}":
            depth += 1
        elif c == "{":
            if depth == 0:
                return i + 1
            depth -= 1
        i -= 1
    return 0


RE_UNSAFE_BLOCK = re.compile(r"\bunsafe\s*(?:\{)")
RE_FROM_UTF8_UNCHECKED = re.compile(
    r"(?<![A-Za-z0-9_])(?:[A-Za-z_][A-Za-z0-9_]*\s*::\s*)*from_utf8_unchecked\s*\("
)


def scan_text_rust(path: Path, text: str) -> list[tuple[Path, int, str, str]]:
    findings: list[tuple[Path, int, str, str]] = []
    cleaned = _strip_strings_and_comments(text)
    pos = 0
    while True:
        m = RE_UNSAFE_BLOCK.search(cleaned, pos)
        if not m:
            break
        # Locate the `{` that opens the unsafe body.
        brace_idx = cleaned.find("{", m.start())
        if brace_idx == -1:
            break
        end = _find_matching(cleaned, brace_idx, "{", "}")
        if end == -1:
            break
        body_clean = cleaned[brace_idx + 1 : end]
        body_orig = text[brace_idx + 1 : end]
        # Establish the enclosing function scope. We approximate it by
        # walking backward from the `unsafe` keyword to find the
        # nearest enclosing `{` that opens a `fn`/`impl`/closure body.
        # If we cannot find one, fall back to the file start.
        fn_scope_start = _find_enclosing_scope_start(cleaned, m.start())
        # Search the body for from_utf8_unchecked calls.
        for cm in RE_FROM_UTF8_UNCHECKED.finditer(body_clean):
            call_offset_in_body = cm.start()
            # Look both at the body *prior* to this call AND at the
            # enclosing function body before the unsafe block.
            prior = (
                cleaned[fn_scope_start:m.start()]
                + body_clean[:call_offset_in_body]
            )
            prior_orig = (
                text[fn_scope_start:m.start()]
                + body_orig[:call_offset_in_body]
            )
            has_validation = False
            for hint in VALIDATION_HINTS:
                if hint in prior or hint in prior_orig:
                    has_validation = True
                    break
            if not has_validation:
                for ah in ASSERT_HINTS:
                    if ah in prior or ah in prior_orig:
                        # Only count if the assert mentions from_utf8 or
                        # is_ascii — generic asserts are not evidence.
                        if (
                            "from_utf8" in prior_orig
                            or "is_ascii" in prior_orig
                            or "utf8_chunks" in prior_orig
                        ):
                            has_validation = True
                            break
            if has_validation:
                continue
            abs_offset = brace_idx + 1 + cm.start()
            lineno = _line_of_offset(cleaned, abs_offset)
            line_str = _line_text(text, lineno)
            # Same-line and one-line-above suppression.
            if (
                SUPPRESS in line_str
                or SUPPRESS in _line_text(text, max(1, lineno - 1))
            ):
                continue
            findings.append(
                (
                    path,
                    lineno,
                    "from-utf8-unchecked-without-validation",
                    line_str.rstrip(),
                )
            )
        pos = end + 1
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
        if lang in ("rust", "rs", ""):
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
