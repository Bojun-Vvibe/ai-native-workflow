#!/usr/bin/env python3
"""Detect SQL queries built with ``fmt.Sprintf`` (or string ``+``
concatenation) and then handed to ``database/sql`` execution methods.

See README.md for full rule list.

Usage
-----
    python3 detect.py <file_or_dir> [...]

Exit ``1`` if any findings, ``0`` otherwise. python3 stdlib only.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

SUPPRESS = "// llm-allow:sprintf-sql-query"

EXEC_METHODS = (
    "Query",
    "QueryRow",
    "Exec",
    "Prepare",
    "QueryContext",
    "QueryRowContext",
    "ExecContext",
    "PrepareContext",
)

SQL_KEYWORDS = (
    "SELECT",
    "INSERT",
    "UPDATE",
    "DELETE",
    "MERGE",
    "WITH ",
    "REPLACE",
    "CREATE",
)

SCAN_SUFFIXES = (".go", ".md", ".markdown")


def _strip_strings_and_comments(text: str) -> tuple[str, list[tuple[int, int]]]:
    """Return (cleaned_text, list_of_string_spans).

    Cleaned text replaces comment bodies with spaces; string-literal
    *contents* are blanked out (quotes preserved). The returned spans
    are (start, end) offsets of original string literal **bodies**
    (between quotes), useful for downstream content lookups.
    """
    out: list[str] = []
    spans: list[tuple[int, int]] = []
    i = 0
    n = len(text)
    in_line_c = False
    in_block_c = False
    in_str: str | None = None  # `"`, "'", or "`" (raw)
    str_body_start = -1
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
            # Raw string: only ` terminates, no escapes.
            if in_str == "`":
                if ch == "`":
                    spans.append((str_body_start, i))
                    out.append("`")
                    in_str = None
                    i += 1
                    continue
                out.append("\n" if ch == "\n" else " ")
                i += 1
                continue
            # Interpreted/rune: handle backslash escapes.
            if ch == "\\" and i + 1 < n:
                out.append("  ")
                i += 2
                continue
            if ch == in_str:
                spans.append((str_body_start, i))
                out.append(in_str)
                in_str = None
                i += 1
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
            in_block_c = True
            out.append("  ")
            i += 2
            continue
        if ch in ('"', "'", "`"):
            in_str = ch
            str_body_start = i + 1
            out.append(ch)
            i += 1
            continue
        out.append(ch)
        i += 1
    return ("".join(out), spans)


# Match `<recv>.<Method>(` where Method is one of EXEC_METHODS. Allow
# any chain on `<recv>` (identifiers, dots, brackets, optional ptr).
RE_EXEC_CALL = re.compile(
    r"\b([A-Za-z_][A-Za-z0-9_]*(?:\s*\.\s*[A-Za-z_][A-Za-z0-9_]*)*)\s*\.\s*("
    + "|".join(EXEC_METHODS)
    + r")\s*\("
)


def _find_matching_paren(text: str, open_idx: int) -> int:
    """Given index of `(`, return index of matching `)`. -1 if not found.
    Operates on cleaned text (strings/comments already blanked), so any
    parens inside literals have been removed.
    """
    depth = 0
    n = len(text)
    i = open_idx
    while i < n:
        c = text[i]
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


def _split_top_level_args(text: str) -> list[str]:
    """Split a comma-separated argument list (without enclosing parens)
    at top-level commas.
    """
    out: list[str] = []
    depth = 0
    cur: list[str] = []
    for ch in text:
        if ch in "({[":
            depth += 1
            cur.append(ch)
        elif ch in ")}]":
            depth -= 1
            cur.append(ch)
        elif ch == "," and depth == 0:
            out.append("".join(cur).strip())
            cur = []
        else:
            cur.append(ch)
    if cur:
        out.append("".join(cur).strip())
    return out


RE_SPRINTF_CALL_HEAD = re.compile(r"\bfmt\s*\.\s*(?:Sprintf|Sprint)\s*\(")
RE_CONTEXT_ARG = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]*$")


def _has_sql_keyword(s: str) -> bool:
    up = s.upper()
    return any(kw in up for kw in SQL_KEYWORDS)


def _line_of_offset(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _line_text(text: str, lineno: int) -> str:
    lines = text.splitlines()
    if 1 <= lineno <= len(lines):
        return lines[lineno - 1]
    return ""


def _expr_contains_sprintf_with_sql(
    expr_clean: str, expr_orig: str
) -> bool:
    """Return True if ``expr`` is (or starts with) a fmt.Sprintf/Sprint
    call whose format-string contains a SQL keyword.
    """
    m = RE_SPRINTF_CALL_HEAD.search(expr_clean)
    if not m:
        return False
    open_idx = expr_clean.find("(", m.start())
    if open_idx == -1:
        return False
    close_idx = _find_matching_paren(expr_clean, open_idx)
    if close_idx == -1:
        return False
    args = _split_top_level_args(expr_clean[open_idx + 1 : close_idx])
    if not args:
        return False
    # The original-text version of the format string is needed to read
    # SQL keywords (the cleaned text has them blanked out).
    orig_open = expr_orig.find("(", m.start())
    if orig_open == -1:
        return False
    orig_close = _find_matching_paren(
        expr_orig.replace("\n", " "), orig_open
    )
    # Fall back: just look at the raw expr_orig for any SQL keyword
    # appearing between the opening paren and the matching close.
    fmt_region = expr_orig[orig_open:]
    return _has_sql_keyword(fmt_region)


def _expr_is_concat_with_sql(expr_clean: str, expr_orig: str) -> bool:
    """Return True if ``expr`` is a `+` concatenation containing at
    least one Go string literal with a SQL keyword **and** at least one
    non-string-literal operand.
    """
    if "+" not in expr_clean:
        return False
    # Original must contain a SQL keyword inside a string literal.
    if not _has_sql_keyword(expr_orig):
        return False
    # Must have at least one identifier-shaped operand (not all literals).
    # Split on `+` at depth 0.
    operands: list[str] = []
    depth = 0
    cur: list[str] = []
    for ch in expr_clean:
        if ch in "({[":
            depth += 1
            cur.append(ch)
        elif ch in ")}]":
            depth -= 1
            cur.append(ch)
        elif ch == "+" and depth == 0:
            operands.append("".join(cur).strip())
            cur = []
        else:
            cur.append(ch)
    if cur:
        operands.append("".join(cur).strip())
    if len(operands) < 2:
        return False
    has_nonliteral = False
    for op in operands:
        s = op.strip()
        if not s:
            continue
        # In cleaned text, string literals are just `"  "` or "`  `" with
        # blanked interior. A literal operand looks like "" or `` (only
        # quote chars + whitespace). Anything else is an identifier,
        # call, etc.
        no_q = s.replace('"', "").replace("`", "").strip()
        if no_q:
            has_nonliteral = True
            break
    return has_nonliteral


def scan_text_go(path: Path, text: str) -> list[tuple[Path, int, str, str]]:
    findings: list[tuple[Path, int, str, str]] = []
    cleaned, _spans = _strip_strings_and_comments(text)
    pos = 0
    while True:
        m = RE_EXEC_CALL.search(cleaned, pos)
        if not m:
            break
        open_idx = cleaned.find("(", m.end() - 1)
        if open_idx == -1:
            pos = m.end()
            continue
        close_idx = _find_matching_paren(cleaned, open_idx)
        if close_idx == -1:
            pos = m.end()
            continue
        arg_clean = cleaned[open_idx + 1 : close_idx]
        arg_orig = text[open_idx + 1 : close_idx]
        args_clean = _split_top_level_args(arg_clean)
        args_orig = _split_top_level_args(arg_orig)
        if not args_clean:
            pos = close_idx + 1
            continue
        # Skip leading context.Context-shaped argument for *Context methods.
        sql_idx = 0
        if (
            m.group(2).endswith("Context")
            and len(args_clean) >= 2
            and RE_CONTEXT_ARG.match(args_clean[0])
        ):
            sql_idx = 1
        if sql_idx >= len(args_clean):
            pos = close_idx + 1
            continue
        sql_clean = args_clean[sql_idx]
        sql_orig = args_orig[sql_idx] if sql_idx < len(args_orig) else ""

        kind: str | None = None
        if _expr_contains_sprintf_with_sql(sql_clean, sql_orig):
            kind = "sprintf-sql-into-exec"
        elif _expr_is_concat_with_sql(sql_clean, sql_orig):
            kind = "concat-sql-into-exec"

        if kind:
            lineno = _line_of_offset(cleaned, m.start())
            end_line = _line_of_offset(cleaned, close_idx)
            suppressed = any(
                SUPPRESS in _line_text(text, ln)
                for ln in range(max(1, lineno - 1), end_line + 1)
            )
            if not suppressed:
                findings.append(
                    (path, lineno, kind, _line_text(text, lineno).rstrip())
                )
        pos = close_idx + 1
    return findings


RE_FENCE_OPEN = re.compile(r"(?m)^([`~]{3,})[ \t]*([A-Za-z0-9_+\-./]*)[^\n]*$")


def _md_extract_go(text: str) -> list[tuple[int, int]]:
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
        if lang in ("go", "golang", ""):
            out.append((body_start, cm.start()))
        pos = cm.end()


def scan_text_md(path: Path, text: str) -> list[tuple[Path, int, str, str]]:
    findings: list[tuple[Path, int, str, str]] = []
    for body_start, body_end in _md_extract_go(text):
        body = text[body_start:body_end]
        sub = scan_text_go(path, body)
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
    return scan_text_go(path, text)


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
