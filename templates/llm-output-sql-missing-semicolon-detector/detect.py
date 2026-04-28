#!/usr/bin/env python3
"""llm-output-sql-missing-semicolon-detector.

Pure-stdlib, code-fence-aware detector for SQL blocks emitted by an
LLM where one or more statements are missing the terminating
semicolon.

Why it matters
--------------
LLMs frequently emit SQL like::

    CREATE TABLE users (id INT, name TEXT);
    INSERT INTO users VALUES (1, 'a')
    INSERT INTO users VALUES (2, 'b');

The middle statement has no `;`. Most CLI clients (psql, mysql,
sqlite3) will then either silently merge the next line into a single
statement, raise a confusing parse error, or — worst — execute only
half of the script. The bug is invisible to the LLM because there's
no parser in the loop; this detector flags it at emit time.

Usage
-----
    python3 detect.py <markdown_file>

Reads the markdown file, finds fenced code blocks whose info-string
first token (case-insensitive) is one of {sql, psql, mysql, sqlite,
sqlite3, postgres, postgresql, plsql, tsql}, splits the body into
top-level statements (semicolon-terminated, with quote/comment
awareness), and reports every statement that has SQL content but no
terminating `;`.

Output: one finding per line on stdout, of the form::

    block=<N> line=<L> kind=missing_semicolon snippet=<first 40 chars>

A trailing summary `total_findings=<N> blocks_checked=<M>` is printed
to stderr. Exit code 0 if no findings, 1 if any.

What it flags
-------------
    missing_semicolon   A statement contains a recognized SQL verb
                        (SELECT/INSERT/UPDATE/DELETE/CREATE/DROP/
                        ALTER/WITH/MERGE/REPLACE/TRUNCATE/GRANT/
                        REVOKE/BEGIN/COMMIT/ROLLBACK/SET/USE) at the
                        start of a logical line and is followed by
                        another statement (or the end of the block)
                        without an intervening `;`.

Out of scope (deliberately): nested BEGIN/END blocks in stored
procedures, dialect-specific delimiters like MySQL `DELIMITER //`,
and statements that legitimately omit `;` because the dialect
allows it. This is a *style/safety* check for LLM output, not a
SQL parser.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import List, Tuple


_SQL_TAGS = {
    "sql", "psql", "mysql", "sqlite", "sqlite3",
    "postgres", "postgresql", "plsql", "tsql",
}

_SQL_VERBS = {
    "select", "insert", "update", "delete", "create", "drop",
    "alter", "with", "merge", "replace", "truncate", "grant",
    "revoke", "begin", "commit", "rollback", "set", "use",
    "explain", "analyze", "vacuum", "pragma",
}


@dataclass(frozen=True)
class Finding:
    block_idx: int
    line_no: int
    snippet: str


def extract_sql_blocks(src: str) -> List[Tuple[int, int, str]]:
    """Return list of (block_idx, start_line_no, body) for each SQL block.

    start_line_no is the 1-indexed line of the first line *inside*
    the fence.
    """
    blocks: List[Tuple[int, int, str]] = []
    lines = src.splitlines()
    i = 0
    in_fence = False
    fence_char = ""
    fence_len = 0
    fence_tag = ""
    body: List[str] = []
    body_start = 0
    block_idx = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.lstrip()
        if not in_fence:
            if stripped.startswith("```") or stripped.startswith("~~~"):
                ch = stripped[0]
                run = 0
                while run < len(stripped) and stripped[run] == ch:
                    run += 1
                if run >= 3:
                    info = stripped[run:].strip()
                    tag = info.split()[0].lower() if info else ""
                    in_fence = True
                    fence_char = ch
                    fence_len = run
                    fence_tag = tag
                    body = []
                    body_start = i + 2
                    i += 1
                    continue
            i += 1
            continue
        # in_fence: look for closing fence (run of fence_char of length >= fence_len)
        s = stripped.rstrip()
        if s and set(s) == {fence_char} and len(s) >= fence_len:
            if fence_tag in _SQL_TAGS:
                block_idx += 1
                blocks.append((block_idx, body_start, "\n".join(body)))
            in_fence = False
            fence_tag = ""
            i += 1
            continue
        body.append(line)
        i += 1
    if in_fence and fence_tag in _SQL_TAGS:
        block_idx += 1
        blocks.append((block_idx, body_start, "\n".join(body)))
    return blocks


def _strip_for_scan(body: str) -> str:
    """Replace string literals and comments with spaces of the same length.

    This makes top-level `;` detection trivial without losing line
    numbers.
    """
    out = []
    i = 0
    n = len(body)
    while i < n:
        c = body[i]
        # line comment --
        if c == "-" and i + 1 < n and body[i + 1] == "-":
            while i < n and body[i] != "\n":
                out.append(" ")
                i += 1
            continue
        # block comment /* */
        if c == "/" and i + 1 < n and body[i + 1] == "*":
            out.append(" ")
            out.append(" ")
            i += 2
            while i < n and not (body[i] == "*" and i + 1 < n and body[i + 1] == "/"):
                out.append("\n" if body[i] == "\n" else " ")
                i += 1
            if i < n:
                out.append(" ")
                out.append(" ")
                i += 2
            continue
        # single-quoted string with '' escape
        if c == "'":
            out.append(" ")
            i += 1
            while i < n:
                if body[i] == "'" and i + 1 < n and body[i + 1] == "'":
                    out.append(" ")
                    out.append(" ")
                    i += 2
                    continue
                if body[i] == "'":
                    out.append(" ")
                    i += 1
                    break
                out.append("\n" if body[i] == "\n" else " ")
                i += 1
            continue
        # double-quoted identifier
        if c == '"':
            out.append(" ")
            i += 1
            while i < n and body[i] != '"':
                out.append("\n" if body[i] == "\n" else " ")
                i += 1
            if i < n:
                out.append(" ")
                i += 1
            continue
        out.append(c)
        i += 1
    return "".join(out)


def detect_in_block(body: str) -> List[Tuple[int, str]]:
    """Return list of (line_no, snippet) findings within one SQL block.

    Walks the (string- and comment-stripped) body line by line. Tracks
    the statement currently being accumulated. When a new verb-led
    line begins while the running statement has non-whitespace content
    that does not end with `;`, that running statement is reported as
    missing its terminator. Same check applies at end-of-block.

    line_no is 1-indexed within the block, pointing at the FIRST line
    of the offending statement.
    """
    findings: List[Tuple[int, str]] = []
    scan = _strip_for_scan(body)
    scan_lines = scan.split("\n")
    orig_lines = body.split("\n")

    cur_start_line: int = -1     # 1-indexed line of first content of current stmt
    cur_scan: List[str] = []     # accumulated scan text of current stmt
    cur_orig: List[str] = []     # accumulated original text

    def flush_unterminated() -> None:
        joined_scan = "\n".join(cur_scan)
        if not joined_scan.strip():
            return
        if joined_scan.rstrip().endswith(";"):
            return
        joined_orig = "\n".join(cur_orig)
        snippet = " ".join(joined_orig.split())[:40]
        findings.append((cur_start_line, snippet))

    for idx, scan_line in enumerate(scan_lines):
        orig_line = orig_lines[idx] if idx < len(orig_lines) else ""
        stripped = scan_line.strip()
        is_blank = not stripped
        first_word = ""
        if not is_blank:
            first_word = stripped.split(None, 1)[0].lower().rstrip(",;()")
        starts_new_stmt = first_word in _SQL_VERBS

        if starts_new_stmt:
            # finishing previous stmt
            flush_unterminated()
            cur_scan = [scan_line]
            cur_orig = [orig_line]
            cur_start_line = idx + 1
            # if this single line itself ends with ; the stmt is complete
            if scan_line.rstrip().endswith(";"):
                cur_scan = []
                cur_orig = []
                cur_start_line = -1
            continue

        if not cur_scan and is_blank:
            continue

        # continuation of current stmt (or blank inside it)
        cur_scan.append(scan_line)
        cur_orig.append(orig_line)
        if scan_line.rstrip().endswith(";"):
            # stmt complete
            cur_scan = []
            cur_orig = []
            cur_start_line = -1

    # tail
    flush_unterminated()
    return findings


def main(argv: List[str]) -> int:
    if len(argv) != 2:
        print("usage: detect.py <markdown_file>", file=sys.stderr)
        return 2
    with open(argv[1], "r", encoding="utf-8") as fh:
        src = fh.read()
    blocks = extract_sql_blocks(src)
    total = 0
    for block_idx, _start, body in blocks:
        for lineno, snippet in detect_in_block(body):
            total += 1
            print(f"block={block_idx} line={lineno} "
                  f"kind=missing_semicolon snippet={snippet!r}")
    print(f"total_findings={total} blocks_checked={len(blocks)}",
          file=sys.stderr)
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
