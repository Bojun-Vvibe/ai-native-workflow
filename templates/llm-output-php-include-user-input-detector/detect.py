#!/usr/bin/env python3
"""Detect PHP local-file-inclusion (LFI) shapes where ``include``,
``include_once``, ``require``, ``require_once`` (or their explicit
function-call forms) take an argument derived from a request superglobal
without any apparent allowlist or sanitization.

Concretely, a finding is emitted when the include target expression
references one of the request-tainted superglobals:

    $_GET, $_POST, $_REQUEST, $_COOKIE, $_FILES, $_SERVER

…and the same expression does **not** include a hard-coded extension
literal that pins the target (e.g. ``. ".php"``, concatenation with a
constant suffix), nor does it pass through ``basename(``,
``realpath(``, an ``in_array(`` allowlist, a ``preg_match(`` whitelist,
or a ``MY_ALLOW`` array lookup heuristic.

Examples flagged:

    include $_GET['page'];
    include_once "pages/" . $_REQUEST['p'] . ".php";  // still tainted
    require __DIR__ . "/" . $_GET['tpl'];
    require_once($_POST['mod']);

Examples NOT flagged:

    include __DIR__ . "/pages/home.php";
    $page = basename($_GET['page']);
    include "pages/" . $page . ".php";
    if (in_array($p, ALLOWED_PAGES)) { include "pages/$p.php"; }

(``basename``, ``realpath``, ``in_array``, ``preg_match`` mitigation
heuristics are intentionally lenient — the goal is to flag the obvious
unfiltered shape an LLM emits.)

Suppress with ``// llm-allow:php-include-tainted`` on the same logical
line.

Stdlib only. Exit 1 if any findings, 0 otherwise.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

SUPPRESS = "// llm-allow:php-include-tainted"

INCLUDES = ("include_once", "require_once", "include", "require")

TAINTED = (
    r"\$_GET",
    r"\$_POST",
    r"\$_REQUEST",
    r"\$_COOKIE",
    r"\$_FILES",
    r"\$_SERVER",
)
RE_TAINTED = re.compile("|".join(TAINTED))

# Mitigation heuristics — if any of these appear in the include
# expression, suppress the finding.
RE_MITIGATIONS = re.compile(
    r"\b(basename|realpath|in_array|preg_match|array_key_exists|"
    r"hash_equals|filter_var)\s*\("
)

SCAN_SUFFIXES = (".php", ".phtml", ".md", ".markdown")


def _strip_php_strings_and_comments(text: str) -> str:
    """Mask PHP comments (``//``, ``#``, ``/* */``) and string literal
    interiors. Keeps newlines + delimiters. Does NOT enter heredoc.
    Heredoc / nowdoc bodies are conservatively masked as plain text
    (they almost never contain include statements).
    """
    out: list[str] = []
    i = 0
    n = len(text)
    in_line_c = False
    in_block_c = False
    in_str: str | None = None  # `"` or `'`
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
        if in_str is not None:
            if c == "\\" and i + 1 < n and in_str == '"':
                out.append("  ")
                i += 2
                continue
            if c == "\\" and nxt == "'" and in_str == "'":
                out.append("  ")
                i += 2
                continue
            if c == in_str:
                out.append(in_str)
                in_str = None
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
        if c == "#" and nxt != "[":
            in_line_c = True
            out.append(" ")
            i += 1
            continue
        if c == "/" and nxt == "*":
            in_block_c = True
            out.append("  ")
            i += 2
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


# Match include / include_once / require / require_once at a word
# boundary, optionally followed by `(` (call form) or whitespace.
RE_INCLUDE_HEAD = re.compile(
    r"\b(" + "|".join(INCLUDES) + r")\b\s*(\(?)"
)


def _read_include_expr(cleaned: str, start: int) -> tuple[int, int]:
    """Given offset of the char right after the include keyword's
    optional ``(``, return ``(expr_start, expr_end)`` covering the
    expression up to the matching ``)`` (call form) or to the
    statement-terminating ``;`` at depth 0 (statement form).
    """
    n = len(cleaned)
    # Skip leading whitespace.
    while start < n and cleaned[start] in " \t\r\n":
        start += 1
    expr_start = start
    depth = 0
    i = start
    paren_form = False
    # If start points at '(', remember so.
    # (We pre-skipped the optional `(` in caller; here we must handle
    # both shapes.)
    while i < n:
        c = cleaned[i]
        if c in "({[":
            depth += 1
        elif c in ")}]":
            if depth == 0:
                # Reached enclosing `)` — terminate (call form caller).
                return (expr_start, i)
            depth -= 1
        elif c == ";" and depth == 0:
            return (expr_start, i)
        i += 1
    return (expr_start, n)


def scan_text_php(path: Path, text: str) -> list[tuple[Path, int, str, str]]:
    findings: list[tuple[Path, int, str, str]] = []
    cleaned = _strip_php_strings_and_comments(text)
    pos = 0
    while True:
        m = RE_INCLUDE_HEAD.search(cleaned, pos)
        if not m:
            break
        kw = m.group(1)
        after = m.end()
        # `include(` or `include (`. If we see `(`, descend one paren
        # and read until matching `)`. Otherwise read until `;`.
        # m.group(2) is the optional `(` captured.
        if m.group(2) == "(":
            # We need to find the matching `)` for the call form.
            depth = 1
            i = after
            n = len(cleaned)
            expr_start = i
            while i < n and depth > 0:
                c = cleaned[i]
                if c in "({[":
                    depth += 1
                elif c in ")}]":
                    depth -= 1
                    if depth == 0:
                        break
                i += 1
            expr_end = i
        else:
            expr_start, expr_end = _read_include_expr(cleaned, after)

        expr_clean = cleaned[expr_start:expr_end]
        expr_orig = text[expr_start:expr_end]
        if RE_TAINTED.search(expr_clean):
            if not RE_MITIGATIONS.search(expr_clean):
                ln = _line_of(text, m.start())
                end_ln = _line_of(text, expr_end)
                suppressed = any(
                    SUPPRESS in _line_text(text, k)
                    for k in range(max(1, ln - 1), end_ln + 1)
                )
                if not suppressed:
                    findings.append(
                        (
                            path,
                            ln,
                            f"php-{kw.replace('_', '-')}-tainted",
                            _line_text(text, ln).rstrip(),
                        )
                    )
        pos = expr_end + 1
    return findings


RE_FENCE_OPEN = re.compile(r"(?m)^([`~]{3,})[ \t]*([A-Za-z0-9_+\-./]*)[^\n]*$")


def _md_extract_php(text: str) -> list[tuple[int, int]]:
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
        if lang in ("php", "phtml", ""):
            out.append((body_start, cm.start()))
        pos = cm.end()


def scan_text_md(path: Path, text: str) -> list[tuple[Path, int, str, str]]:
    findings: list[tuple[Path, int, str, str]] = []
    for body_start, body_end in _md_extract_php(text):
        body = text[body_start:body_end]
        sub = scan_text_php(path, body)
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
    return scan_text_php(path, text)


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
