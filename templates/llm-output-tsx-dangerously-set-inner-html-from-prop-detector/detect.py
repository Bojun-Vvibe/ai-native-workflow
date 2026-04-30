#!/usr/bin/env python3
"""Detect ``dangerouslySetInnerHTML`` whose ``__html`` flows from
caller-controlled inputs in LLM-emitted React/TSX code.

See README.md for the full rule list.

Usage
-----
    python3 detect.py <file_or_dir> [...]

Exit ``1`` if any findings, ``0`` otherwise. python3 stdlib only.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

SUPPRESS = "// llm-allow:dangerously-set-inner-html"

# Names that are treated as untrusted sources when they appear inside the
# `__html:` expression. Matched as identifiers (whole-word, optionally
# followed by `.`, `?.`, or `[`).
SOURCE_TOKENS = (
    "props",
    "req",
    "request",
    "searchParams",
    "params",
    "router",
    "useRouter",
    "useSearchParams",
    "useParams",
    "location",
    "window",
    "document",
    "localStorage",
    "sessionStorage",
    "URL",
)

# Field-style names that, alone, suggest user content (used when the
# expression is just an identifier with no obvious source qualifier).
LIKELY_USER_CONTENT_NAMES = (
    "html",
    "content",
    "body",
    "bio",
    "description",
    "markdown",
    "raw",
    "comment",
    "message",
    "note",
    "text",
    "value",
    "payload",
    "data",
    "userInput",
    "input",
    "summary",
    "snippet",
)

SANITIZER_TOKENS = (
    r"DOMPurify\s*\.\s*sanitize",
    r"DOMPurify",
    r"sanitizeHtml",
    r"sanitize_html",
    r"purify",
    r"xss",
    r"escapeHtml",
    r"escape_html",
    r"stripHtml",
)

RE_DANGEROUS = re.compile(
    r"dangerouslySetInnerHTML\s*=\s*\{\s*\{\s*__html\s*:\s*(.+?)\s*\}\s*\}",
    re.DOTALL,
)

RE_SOURCE = re.compile(
    r"\b(?:" + "|".join(re.escape(t) for t in SOURCE_TOKENS) + r")\b"
)
RE_USER_CONTENT_NAME = re.compile(
    r"\b(?:" + "|".join(re.escape(t) for t in LIKELY_USER_CONTENT_NAMES) + r")\b"
)
RE_SANITIZER = re.compile(
    r"(?:" + "|".join(SANITIZER_TOKENS) + r")\s*\("
)
RE_IDENTIFIER_ONLY = re.compile(r"^[A-Za-z_$][A-Za-z0-9_$]*$")


def _strip_strings_and_comments(text: str) -> str:
    """Remove // and /* */ comments and replace string-literal contents
    with spaces. Backtick template literals: keep the backticks but blank
    out interior text *outside* of `${...}` substitutions, since the
    substitutions are real code we want to scan.
    """
    out: list[str] = []
    i = 0
    n = len(text)
    in_line_c = False
    in_block_c = False
    in_str: str | None = None  # `'`, `"`, or "`"
    tmpl_depth = 0  # depth of `${...}` inside a backtick template
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
        if in_block_c:
            if ch == "*" and nxt == "/":
                in_block_c = False
                out.append("  ")
                i += 2
                continue
            out.append("\n" if ch == "\n" else " ")
            i += 1
            continue
        if in_str is not None:
            if in_str == "`" and ch == "$" and nxt == "{":
                tmpl_depth += 1
                out.append("${")
                i += 2
                in_str = None  # drop into code mode while inside ${...}
                continue
            if ch == "\\" and i + 1 < n:
                out.append("  ")
                i += 2
                continue
            if ch == in_str:
                out.append(in_str)
                in_str = None
                i += 1
                continue
            out.append("\n" if ch == "\n" else " ")
            i += 1
            continue
        # not in any string / comment
        if ch == "/" and nxt == "/":
            in_line_c = True
            out.append("  ")
            i += 2
            continue
        if ch == "/" and nxt == "*":
            in_block_c = True
            out.append("  ")
            i += 2
            continue
        if ch in ("'", '"', "`"):
            in_str = ch
            out.append(ch)
            i += 1
            continue
        if tmpl_depth > 0 and ch == "}":
            tmpl_depth -= 1
            out.append("}")
            in_str = "`"
            i += 1
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def _expr_is_unsafe(expr: str) -> str | None:
    """Given the expression after ``__html:``, return finding-kind if
    unsafe, else ``None``.
    """
    e = expr.strip().rstrip(",;")
    if not e:
        return None
    if RE_SANITIZER.search(e):
        return None
    if RE_SOURCE.search(e):
        return "html-from-untrusted-source"
    # Bare identifier matching a user-content-shaped name? Treat as
    # destructured-prop case (the function signature usually destructures
    # the prop). Conservative — exclude obvious literals/method calls.
    if RE_IDENTIFIER_ONLY.match(e) and RE_USER_CONTENT_NAME.search(e):
        return "html-from-user-content-named-identifier"
    return None


def _line_of_offset(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _line_text(text: str, lineno: int) -> str:
    lines = text.splitlines()
    if 1 <= lineno <= len(lines):
        return lines[lineno - 1]
    return ""


# Markdown fenced-code extraction: yield (start_offset, end_offset, lang)
# of each fenced block body.
RE_FENCE_OPEN = re.compile(r"(?m)^([`~]{3,})[ \t]*([A-Za-z0-9_+\-./]*)[^\n]*$")


def _md_extract_code(text: str) -> list[tuple[int, int, str]]:
    out: list[tuple[int, int, str]] = []
    pos = 0
    while True:
        m = RE_FENCE_OPEN.search(text, pos)
        if not m:
            return out
        fence = m.group(1)
        lang = (m.group(2) or "").lower()
        body_start = m.end() + 1  # skip newline after fence line
        # Find matching close fence (same char, length >= open).
        close_re = re.compile(
            r"(?m)^" + fence[0] + "{" + str(len(fence)) + r",}[ \t]*$"
        )
        cm = close_re.search(text, body_start)
        if not cm:
            return out
        out.append((body_start, cm.start(), lang))
        pos = cm.end()


def scan_text_jslike(path: Path, text: str) -> list[tuple[Path, int, str, str]]:
    findings: list[tuple[Path, int, str, str]] = []
    cleaned = _strip_strings_and_comments(text)
    for m in RE_DANGEROUS.finditer(cleaned):
        expr = m.group(1)
        kind = _expr_is_unsafe(expr)
        if not kind:
            continue
        lineno = _line_of_offset(cleaned, m.start())
        # Suppression: marker on any line within the match span, OR on the
        # line immediately preceding the match.
        end_line = _line_of_offset(cleaned, m.end())
        suppressed = any(
            SUPPRESS in _line_text(text, ln)
            for ln in range(max(1, lineno - 1), end_line + 1)
        )
        if suppressed:
            continue
        findings.append((path, lineno, kind, _line_text(text, lineno).rstrip()))
    return findings


def scan_text_md(path: Path, text: str) -> list[tuple[Path, int, str, str]]:
    findings: list[tuple[Path, int, str, str]] = []
    for body_start, body_end, lang in _md_extract_code(text):
        if lang not in ("tsx", "jsx", "ts", "js", "javascript", "typescript", ""):
            continue
        body = text[body_start:body_end]
        sub_findings = scan_text_jslike(path, body)
        # Adjust line numbers from body-relative to file-absolute.
        offset_lines = text.count("\n", 0, body_start)
        for p, ln, kind, line in sub_findings:
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
    return scan_text_jslike(path, text)


SCAN_SUFFIXES = (".tsx", ".jsx", ".ts", ".js", ".md", ".markdown")


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
