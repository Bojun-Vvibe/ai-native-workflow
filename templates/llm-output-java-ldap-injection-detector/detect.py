#!/usr/bin/env python3
"""Detect LDAP search filters built via string concatenation /
String.format and passed to a JNDI-style ``.search(...)`` call.

See README.md for the rationale. python3 stdlib only.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

SUPPRESS = "llm-allow:ldap-injection"
SCAN_SUFFIXES = (".java", ".md", ".markdown")

SAFE_HINTS = (
    "Filter.create",
    "Filter.createANDFilter",
    "Filter.createORFilter",
    "Filter.encodeValue",
    "escapeLDAPSearchFilter",
    "escapeLdapFilter",
    "Encode.forLdap",
)


def _strip_strings_and_comments(text: str) -> tuple[str, str]:
    """Return (no_strings, no_comments).

    ``no_strings``: a copy of ``text`` with string-literal *bodies*
    blanked but the surrounding quotes preserved. Used to find the
    structural ``+`` operators between literals and identifiers.

    ``no_comments``: a copy of ``text`` with ``//`` and ``/* */``
    comment bodies blanked but string literals intact. Used so we can
    still inspect the literal content (for ``(`` and ``)``).

    Newlines are preserved in both, so line numbers stay aligned.
    """
    n = len(text)
    no_strings: list[str] = []
    no_comments: list[str] = []
    i = 0
    in_line_c = False
    in_block_c = False
    in_str = False
    in_char = False
    while i < n:
        ch = text[i]
        nxt = text[i + 1] if i + 1 < n else ""
        if in_line_c:
            if ch == "\n":
                in_line_c = False
                no_strings.append("\n")
                no_comments.append("\n")
            else:
                no_strings.append(ch)
                no_comments.append(" ")
            i += 1
            continue
        if in_block_c:
            if ch == "*" and nxt == "/":
                in_block_c = False
                no_strings.append("  ")
                no_comments.append("  ")
                i += 2
                continue
            no_strings.append("\n" if ch == "\n" else ch)
            no_comments.append("\n" if ch == "\n" else " ")
            i += 1
            continue
        if in_str:
            no_comments.append(ch)
            if ch == "\\" and i + 1 < n:
                no_strings.append("  ")
                no_comments.append(text[i + 1])
                i += 2
                continue
            if ch == '"':
                no_strings.append('"')
                in_str = False
                i += 1
                continue
            no_strings.append("\n" if ch == "\n" else " ")
            i += 1
            continue
        if in_char:
            no_comments.append(ch)
            if ch == "\\" and i + 1 < n:
                no_strings.append("  ")
                no_comments.append(text[i + 1])
                i += 2
                continue
            if ch == "'":
                no_strings.append("'")
                in_char = False
                i += 1
                continue
            no_strings.append(" ")
            i += 1
            continue
        if ch == "/" and nxt == "/":
            in_line_c = True
            no_strings.append("  ")
            no_comments.append("  ")
            i += 2
            continue
        if ch == "/" and nxt == "*":
            in_block_c = True
            no_strings.append("  ")
            no_comments.append("  ")
            i += 2
            continue
        if ch == '"':
            in_str = True
            no_strings.append('"')
            no_comments.append('"')
            i += 1
            continue
        if ch == "'":
            in_char = True
            no_strings.append("'")
            no_comments.append("'")
            i += 1
            continue
        no_strings.append(ch)
        no_comments.append(ch)
        i += 1
    return "".join(no_strings), "".join(no_comments)


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


def _split_top_level_args(s: str) -> list[str]:
    """Split a comma-separated argument list at depth 0."""
    out: list[str] = []
    buf: list[str] = []
    depth = 0
    in_str = False
    i = 0
    n = len(s)
    while i < n:
        c = s[i]
        if in_str:
            if c == "\\" and i + 1 < n:
                buf.append(c); buf.append(s[i + 1]); i += 2; continue
            if c == '"':
                in_str = False
            buf.append(c); i += 1; continue
        if c == '"':
            in_str = True; buf.append(c); i += 1; continue
        if c in "([{<":
            depth += 1; buf.append(c); i += 1; continue
        if c in ")]}>":
            depth -= 1; buf.append(c); i += 1; continue
        if c == "," and depth == 0:
            out.append("".join(buf).strip()); buf = []; i += 1; continue
        buf.append(c); i += 1
    tail = "".join(buf).strip()
    if tail:
        out.append(tail)
    return out


# Receiver name ends in Context / Ctx (case-insensitive) — typical of
# DirContext / LdapContext / InitialDirContext.
RE_SEARCH_CALL = re.compile(
    r"(?P<recv>[A-Za-z_][A-Za-z0-9_]*)\s*\.\s*search\s*\("
)

RE_FORMAT_CALL = re.compile(r"\bString\s*\.\s*format\s*\(")
RE_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
RE_LITERAL_CONCAT_ASSIGN = re.compile(
    r"\bString\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*=\s*(?P<rhs>[^;]+);"
)


def _is_safe_filter_expr(expr: str) -> bool:
    return any(h in expr for h in SAFE_HINTS)


def _looks_like_concat_filter(expr_no_str: str, expr_orig: str) -> bool:
    """Heuristic: filter expression is a `+`-concatenation of a string
    literal that contains `(` with at least one non-literal token."""
    if "+" not in expr_no_str:
        return False
    # Must have a literal containing `(` somewhere in the original.
    if not re.search(r'"[^"]*\([^"]*"', expr_orig):
        return False
    return True


def _looks_like_format_filter(expr_orig: str) -> bool:
    if not RE_FORMAT_CALL.search(expr_orig):
        return False
    # The format string (first arg) must contain `(` and a `%` directive.
    m = RE_FORMAT_CALL.search(expr_orig)
    if not m:
        return False
    open_paren = expr_orig.find("(", m.end() - 1)
    if open_paren == -1:
        return False
    end = _find_matching(expr_orig, open_paren, "(", ")")
    if end == -1:
        return False
    args = _split_top_level_args(expr_orig[open_paren + 1:end])
    if not args:
        return False
    fmt = args[0]
    if "(" in fmt and re.search(r"%[sdc]", fmt):
        return True
    return False


def scan_text_java(path: Path, text: str) -> list[tuple[Path, int, str, str]]:
    findings: list[tuple[Path, int, str, str]] = []
    no_strings, no_comments = _strip_strings_and_comments(text)

    # Build a map of `String name = <rhs>;` assignments where rhs is a
    # `+`-concatenated literal with `(` AND no safe-hint appears.
    unsafe_idents: dict[str, int] = {}
    safe_idents: set[str] = set()
    for am in RE_LITERAL_CONCAT_ASSIGN.finditer(no_comments):
        rhs = am.group("rhs")
        rhs_no_strings = no_strings[am.start("rhs"):am.end("rhs")]
        name = am.group("name")
        if _is_safe_filter_expr(rhs):
            safe_idents.add(name)
            continue
        if _looks_like_concat_filter(rhs_no_strings, rhs):
            unsafe_idents[name] = _line_of_offset(text, am.start())

    for sm in RE_SEARCH_CALL.finditer(no_comments):
        recv = sm.group("recv")
        if not re.search(r"(?:ctx|context|ldapcontext|dircontext)$", recv, re.IGNORECASE):
            continue
        open_paren = sm.end() - 1
        close = _find_matching(no_comments, open_paren, "(", ")")
        if close == -1:
            continue
        args_orig = no_comments[open_paren + 1:close]
        args_no_strings = no_strings[open_paren + 1:close]
        args = _split_top_level_args(args_orig)
        args_ns = _split_top_level_args(args_no_strings)
        if len(args) < 2:
            continue
        filter_arg = args[1]
        filter_arg_ns = args_ns[1] if len(args_ns) > 1 else ""

        if _is_safe_filter_expr(filter_arg):
            continue
        if RE_IDENT.match(filter_arg) and filter_arg in safe_idents:
            continue

        kind: str | None = None
        if _looks_like_concat_filter(filter_arg_ns, filter_arg):
            kind = "ldap-search-concat-literal"
        elif _looks_like_format_filter(filter_arg):
            kind = "ldap-search-string-format"
        elif RE_IDENT.match(filter_arg) and filter_arg in unsafe_idents:
            kind = "ldap-search-tainted-ident"

        if kind is None:
            continue

        lineno = _line_of_offset(text, sm.start())
        line_str = _line_text(text, lineno)
        # Determine the line of the closing paren for multi-line calls.
        end_lineno = _line_of_offset(text, close)
        suppressed = False
        for ln in range(max(1, lineno - 1), end_lineno + 2):
            if SUPPRESS in _line_text(text, ln):
                suppressed = True
                break
        if suppressed:
            continue
        findings.append((path, lineno, kind, line_str.rstrip()))
    return findings


RE_FENCE_OPEN = re.compile(
    r"(?m)^([`~]{3,})[ \t]*([A-Za-z0-9_+\-./]*)[^\n]*$"
)


def _md_extract_java(text: str) -> list[tuple[int, int]]:
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
        if lang in ("java",):
            out.append((body_start, cm.start()))
        pos = cm.end()


def scan_text_md(path: Path, text: str) -> list[tuple[Path, int, str, str]]:
    findings: list[tuple[Path, int, str, str]] = []
    for body_start, body_end in _md_extract_java(text):
        body = text[body_start:body_end]
        sub = scan_text_java(path, body)
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
    return scan_text_java(path, text)


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
