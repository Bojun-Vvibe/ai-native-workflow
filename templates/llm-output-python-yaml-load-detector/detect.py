#!/usr/bin/env python3
"""Detect Python ``yaml.load`` (or aliased) calls that omit a safe
loader, the canonical CWE-502 (Deserialization of Untrusted Data)
shape PyYAML has warned about for a decade.

A finding is emitted whenever a call shaped like::

    yaml.load(...)
    yaml.load_all(...)

is invoked **without** any of these safe loader hints appearing inside
the call's argument list:

    SafeLoader, CSafeLoader, BaseLoader, CBaseLoader, safe_load,
    Loader=yaml.SafeLoader, Loader=SafeLoader

Examples flagged::

    yaml.load(stream)
    yaml.load(open("conf.yml"))
    yaml.load(stream, Loader=yaml.FullLoader)   # FullLoader is unsafe
    yaml.load(stream, Loader=yaml.Loader)
    yaml.load_all(stream)

Examples NOT flagged::

    yaml.safe_load(stream)
    yaml.load(stream, Loader=yaml.SafeLoader)
    yaml.load(stream, Loader=SafeLoader)
    yaml.load(stream, Loader=yaml.CSafeLoader)
    yaml.load(stream, Loader=yaml.BaseLoader)

Suppress with ``# llm-allow:python-yaml-load-unsafe`` on the same
logical line as the call.

Stdlib only. Exit 1 if any findings, 0 otherwise.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

SUPPRESS = "# llm-allow:python-yaml-load-unsafe"

# yaml.load( or yaml.load_all( where yaml may be any identifier alias
# (e.g. "import yaml as Y" -> Y.load(...)). We match `<id>.load(`
# and `<id>.load_all(` then verify by argument scan.
RE_CALL_HEAD = re.compile(
    r"\b([A-Za-z_][A-Za-z0-9_]*)\.(load|load_all)\s*\("
)

SAFE_HINTS = re.compile(
    r"\b("
    r"SafeLoader|CSafeLoader|BaseLoader|CBaseLoader|safe_load"
    r")\b"
)

SCAN_SUFFIXES = (".py", ".pyi", ".md", ".markdown", ".rst")


def _strip_py_strings_and_comments(text: str) -> str:
    """Mask Python ``#`` comments and string literal interiors so the
    call-shape regex does not match inside docstrings or comments.
    Triple-quoted strings handled. Preserves newlines and quote
    delimiters.
    """
    out: list[str] = []
    i = 0
    n = len(text)
    in_line_c = False
    in_str: str | None = None  # one of '"', "'", '"""', "'''"
    while i < n:
        c = text[i]
        if in_line_c:
            if c == "\n":
                in_line_c = False
                out.append("\n")
            else:
                out.append(" ")
            i += 1
            continue
        if in_str is not None:
            # Triple-quoted close?
            if len(in_str) == 3 and text[i:i + 3] == in_str:
                out.append(in_str)
                in_str = None
                i += 3
                continue
            if len(in_str) == 1 and c == in_str:
                out.append(in_str)
                in_str = None
                i += 1
                continue
            if c == "\\" and i + 1 < n:
                out.append("  ")
                i += 2
                continue
            out.append("\n" if c == "\n" else " ")
            i += 1
            continue
        # Code mode.
        if c == "#":
            in_line_c = True
            out.append(" ")
            i += 1
            continue
        # Triple quotes
        if text[i:i + 3] in ('"""', "'''"):
            in_str = text[i:i + 3]
            out.append(in_str)
            i += 3
            continue
        if c in ('"', "'"):
            in_str = c
            out.append(c)
            i += 1
            continue
        out.append(c)
        i += 1
    return "".join(out)


def _line_of(text: str, off: int) -> int:
    return text.count("\n", 0, off) + 1


def _line_text(text: str, ln: int) -> str:
    lines = text.splitlines()
    if 1 <= ln <= len(lines):
        return lines[ln - 1]
    return ""


def _find_matching_paren(s: str, open_idx: int) -> int:
    """Given index of an opening ``(``, return index of matching
    ``)``, or len(s) if unmatched."""
    depth = 0
    n = len(s)
    i = open_idx
    while i < n:
        c = s[i]
        if c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return n


def scan_text_py(path: Path, text: str) -> list[tuple[Path, int, str, str]]:
    findings: list[tuple[Path, int, str, str]] = []
    cleaned = _strip_py_strings_and_comments(text)
    pos = 0
    while True:
        m = RE_CALL_HEAD.search(cleaned, pos)
        if not m:
            break
        ident = m.group(1)
        fn = m.group(2)
        # Heuristic: skip obviously unrelated identifiers like `json`
        # `pickle` etc. Only look for `yaml`, or any alias literally
        # named `yaml`, or any identifier — we keep this lenient and
        # let the safe-hint check be the primary discriminator. To
        # cut noise, restrict to `yaml` or aliases ending with
        # `yaml` (case-insensitive) OR exactly `Y`/`yml`.
        ident_low = ident.lower()
        if ident_low != "yaml" and not ident_low.endswith("yaml") \
                and ident_low not in ("yml", "y"):
            pos = m.end()
            continue
        open_paren = m.end() - 1  # the `(` we matched
        close = _find_matching_paren(cleaned, open_paren)
        args_clean = cleaned[open_paren + 1:close]
        if SAFE_HINTS.search(args_clean):
            pos = close + 1
            continue
        ln = _line_of(text, m.start())
        end_ln = _line_of(text, close)
        suppressed = any(
            SUPPRESS in _line_text(text, k)
            for k in range(max(1, ln), end_ln + 1)
        )
        if not suppressed:
            kind = f"python-yaml-{fn.replace('_', '-')}-unsafe"
            findings.append((path, ln, kind, _line_text(text, ln).rstrip()))
        pos = close + 1
    return findings


RE_FENCE_OPEN = re.compile(r"(?m)^([`~]{3,})[ \t]*([A-Za-z0-9_+\-./]*)[^\n]*$")


def _md_extract_py(text: str) -> list[tuple[int, int]]:
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
        if lang in ("python", "py", "python3", ""):
            out.append((body_start, cm.start()))
        pos = cm.end()


def scan_text_md(path: Path, text: str) -> list[tuple[Path, int, str, str]]:
    findings: list[tuple[Path, int, str, str]] = []
    for body_start, body_end in _md_extract_py(text):
        body = text[body_start:body_end]
        sub = scan_text_py(path, body)
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
    if suf in (".md", ".markdown", ".rst"):
        return scan_text_md(path, text)
    return scan_text_py(path, text)


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
