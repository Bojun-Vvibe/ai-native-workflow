#!/usr/bin/env python3
"""Detect C# SQL queries built by string concatenation / interpolation
and then handed to ``SqlCommand`` (or sibling ADO.NET command types)
constructors / ``CommandText`` assignments.

Two shapes are flagged:

1. ``new SqlCommand("SELECT ... " + userVar, conn)`` — first arg is a
   ``+`` concatenation containing a SQL keyword in a string literal
   plus at least one non-literal operand.
2. ``cmd.CommandText = "SELECT ... " + userVar;`` — assignment to a
   ``CommandText`` property where the right-hand side is a
   concatenation, a ``$"..."`` interpolated string with placeholders,
   or a ``string.Format(...)`` call, in each case containing a SQL
   keyword.

Recognized command type constructors (heuristic — match on the
identifier name):

    SqlCommand, OracleCommand, OleDbCommand, OdbcCommand,
    SQLiteCommand, MySqlCommand, NpgsqlCommand

Suppress with ``// llm-allow:sqlcommand-concat`` on the same logical
line.

Stdlib only. Exit 1 if any findings, 0 otherwise.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

SUPPRESS = "// llm-allow:sqlcommand-concat"

CMD_TYPES = (
    "SqlCommand",
    "OracleCommand",
    "OleDbCommand",
    "OdbcCommand",
    "SQLiteCommand",
    "MySqlCommand",
    "NpgsqlCommand",
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
    "DROP",
    "ALTER",
    "TRUNCATE",
)

SCAN_SUFFIXES = (".cs", ".md", ".markdown")


def _strip_strings_and_comments(text: str) -> str:
    """Blank string literal *contents* and comment bodies, preserving
    structure (newlines + delimiters). Verbatim strings (``@"..."``)
    only terminate on a single ``"`` (with ``""`` as escape).
    Interpolated strings (``$"..."`` and ``$@"..."``) are treated like
    regular strings for masking purposes — interior is blanked.
    """
    out: list[str] = []
    i = 0
    n = len(text)
    in_line_c = False
    in_block_c = False
    in_str = False
    is_verbatim = False
    while i < n:
        c = text[i]
        nxt = text[i + 1] if i + 1 < n else ""
        if in_line_c:
            if c == "\n":
                in_line_c = False
                out.append("\n")
            else:
                out.append(" ")
            i += 1
            continue
        if in_block_c:
            if c == "*" and nxt == "/":
                in_block_c = False
                out.append("  ")
                i += 2
                continue
            out.append("\n" if c == "\n" else " ")
            i += 1
            continue
        if in_str:
            if is_verbatim:
                if c == '"' and nxt == '"':
                    out.append("  ")
                    i += 2
                    continue
                if c == '"':
                    out.append('"')
                    in_str = False
                    is_verbatim = False
                    i += 1
                    continue
                out.append("\n" if c == "\n" else " ")
                i += 1
                continue
            # Regular interpreted string.
            if c == "\\" and i + 1 < n:
                out.append("  ")
                i += 2
                continue
            if c == '"':
                out.append('"')
                in_str = False
                i += 1
                continue
            out.append("\n" if c == "\n" else " ")
            i += 1
            continue
        # Code mode.
        if c == "/" and nxt == "/":
            in_line_c = True
            out.append("  ")
            i += 2
            continue
        if c == "/" and nxt == "*":
            in_block_c = True
            out.append("  ")
            i += 2
            continue
        # Verbatim or interpolated-verbatim: @"..." / $@"..." / @$"..."
        if c == "@" and nxt == '"':
            in_str = True
            is_verbatim = True
            out.append('@"')
            i += 2
            continue
        if c == "$" and nxt == '"':
            in_str = True
            is_verbatim = False
            out.append('$"')
            i += 2
            continue
        if c == "$" and nxt == "@" and i + 2 < n and text[i + 2] == '"':
            in_str = True
            is_verbatim = True
            out.append('$@"')
            i += 3
            continue
        if c == "@" and nxt == "$" and i + 2 < n and text[i + 2] == '"':
            in_str = True
            is_verbatim = True
            out.append('@$"')
            i += 3
            continue
        if c == '"':
            in_str = True
            is_verbatim = False
            out.append('"')
            i += 1
            continue
        out.append(c)
        i += 1
    return "".join(out)


def _find_matching(text: str, open_idx: int, open_c: str, close_c: str) -> int:
    depth = 0
    n = len(text)
    i = open_idx
    while i < n:
        ch = text[i]
        if ch == open_c:
            depth += 1
        elif ch == close_c:
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


def _split_top_level(text: str, sep: str) -> list[str]:
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
        elif ch == sep and depth == 0:
            out.append("".join(cur).strip())
            cur = []
        else:
            cur.append(ch)
    if cur:
        out.append("".join(cur).strip())
    return out


def _has_sql_keyword(s: str) -> bool:
    up = s.upper()
    return any(kw in up for kw in SQL_KEYWORDS)


def _is_concat_with_sql(expr_clean: str, expr_orig: str) -> bool:
    if "+" not in expr_clean:
        return False
    if not _has_sql_keyword(expr_orig):
        return False
    operands = _split_top_level(expr_clean, "+")
    if len(operands) < 2:
        return False
    for op in operands:
        s = op.strip()
        if not s:
            continue
        # Cleaned literal looks like `""` / `@""` / `$""` after blanking.
        no_q = re.sub(r'[$@"]', "", s).strip()
        if no_q:
            return True
    return False


def _is_interpolated_with_sql(expr_orig: str) -> bool:
    """``$"...{var}..."`` (or ``$@"..."``) containing a SQL keyword
    AND at least one ``{...}`` placeholder."""
    s = expr_orig.lstrip()
    if not (s.startswith('$"') or s.startswith('$@"') or s.startswith('@$"')):
        return False
    if not _has_sql_keyword(expr_orig):
        return False
    # Look for unescaped `{` not followed by another `{`.
    i = 0
    n = len(expr_orig)
    while i < n - 1:
        if expr_orig[i] == "{" and expr_orig[i + 1] != "{":
            return True
        i += 1
    return False


def _is_string_format_with_sql(expr_clean: str, expr_orig: str) -> bool:
    if "string.Format" not in expr_clean and "String.Format" not in expr_clean:
        return False
    return _has_sql_keyword(expr_orig)


def _line_of(text: str, off: int) -> int:
    return text.count("\n", 0, off) + 1


def _line_text(text: str, ln: int) -> str:
    lines = text.splitlines()
    if 1 <= ln <= len(lines):
        return lines[ln - 1]
    return ""


RE_NEW_CMD = re.compile(
    r"\bnew\s+(" + "|".join(CMD_TYPES) + r")\s*\("
)
RE_CMDTEXT_ASSIGN = re.compile(
    r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\.\s*CommandText\s*="
)


def scan_text_cs(path: Path, text: str) -> list[tuple[Path, int, str, str]]:
    findings: list[tuple[Path, int, str, str]] = []
    cleaned = _strip_strings_and_comments(text)

    # Shape 1: new XxxCommand( <sql>, ... )
    pos = 0
    while True:
        m = RE_NEW_CMD.search(cleaned, pos)
        if not m:
            break
        open_idx = cleaned.find("(", m.end() - 1)
        close_idx = _find_matching(cleaned, open_idx, "(", ")")
        if open_idx == -1 or close_idx == -1:
            pos = m.end()
            continue
        args_clean = _split_top_level(cleaned[open_idx + 1 : close_idx], ",")
        args_orig = _split_top_level(text[open_idx + 1 : close_idx], ",")
        if args_clean and args_orig:
            sql_c = args_clean[0]
            sql_o = args_orig[0]
            kind = None
            if _is_concat_with_sql(sql_c, sql_o):
                kind = "sqlcommand-concat"
            elif _is_interpolated_with_sql(sql_o):
                kind = "sqlcommand-interpolation"
            elif _is_string_format_with_sql(sql_c, sql_o):
                kind = "sqlcommand-stringformat"
            if kind:
                ln = _line_of(text, m.start())
                end_ln = _line_of(text, close_idx)
                suppressed = any(
                    SUPPRESS in _line_text(text, k)
                    for k in range(max(1, ln - 1), end_ln + 1)
                )
                if not suppressed:
                    findings.append(
                        (path, ln, kind, _line_text(text, ln).rstrip())
                    )
        pos = close_idx + 1

    # Shape 2: <ident>.CommandText = <expr>;
    pos = 0
    while True:
        m = RE_CMDTEXT_ASSIGN.search(cleaned, pos)
        if not m:
            break
        # Walk forward to ';' at depth 0.
        i = m.end()
        depth = 0
        n = len(cleaned)
        while i < n:
            ch = cleaned[i]
            if ch in "({[":
                depth += 1
            elif ch in ")}]":
                depth -= 1
            elif ch == ";" and depth == 0:
                break
            i += 1
        rhs_c = cleaned[m.end():i].strip()
        rhs_o = text[m.end():i].strip()
        kind = None
        if _is_concat_with_sql(rhs_c, rhs_o):
            kind = "sqlcommand-concat"
        elif _is_interpolated_with_sql(rhs_o):
            kind = "sqlcommand-interpolation"
        elif _is_string_format_with_sql(rhs_c, rhs_o):
            kind = "sqlcommand-stringformat"
        if kind:
            ln = _line_of(text, m.start())
            end_ln = _line_of(text, i)
            suppressed = any(
                SUPPRESS in _line_text(text, k)
                for k in range(max(1, ln - 1), end_ln + 1)
            )
            if not suppressed:
                findings.append(
                    (path, ln, kind, _line_text(text, ln).rstrip())
                )
        pos = i + 1

    return findings


RE_FENCE_OPEN = re.compile(r"(?m)^([`~]{3,})[ \t]*([A-Za-z0-9_+\-./]*)[^\n]*$")


def _md_extract_cs(text: str) -> list[tuple[int, int]]:
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
        if lang in ("cs", "csharp", "c#", ""):
            out.append((body_start, cm.start()))
        pos = cm.end()


def scan_text_md(path: Path, text: str) -> list[tuple[Path, int, str, str]]:
    findings: list[tuple[Path, int, str, str]] = []
    for body_start, body_end in _md_extract_cs(text):
        body = text[body_start:body_end]
        sub = scan_text_cs(path, body)
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
    return scan_text_cs(path, text)


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
