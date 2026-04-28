#!/usr/bin/env python3
"""
llm-output-sql-string-concat-injection-detector

Flags Python source where SQL queries are built via string concatenation,
%-formatting, .format(), or f-strings and then passed to a DB cursor's
execute()/executemany(). These patterns are classic SQL-injection vectors
that LLMs frequently emit when generating data-access code.

Heuristic: scan with the `ast` module, walk Call nodes whose function name
is execute/executemany, and inspect the first argument. If that argument
is a string built dynamically (BinOp with str, JoinedStr/f-string, %-mod,
or .format() call) AND the SQL keyword set is present somewhere in the
literal portion (SELECT/INSERT/UPDATE/DELETE/CREATE/DROP), report it.

Also handles markdown-fenced ```python blocks: extracts each fence and
runs the same AST scan on it.

Exit codes:
  0 - no findings
  1 - findings reported
  2 - usage / read error

Usage:
  python3 detector.py <file> [<file> ...]
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path
from typing import Iterable

SQL_KEYWORDS = re.compile(
    r"\b(SELECT|INSERT|UPDATE|DELETE|CREATE|DROP|ALTER|REPLACE|MERGE)\b",
    re.IGNORECASE,
)

EXECUTE_NAMES = {"execute", "executemany", "executescript"}

FENCE_RE = re.compile(r"^```([a-zA-Z0-9_+\-]*)\s*$")


def _string_pieces(node: ast.AST) -> list[str]:
    """Collect any literal string fragments embedded in the expression."""
    out: list[str] = []
    for sub in ast.walk(node):
        if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
            out.append(sub.value)
    return out


def _is_dynamic_sql(arg: ast.AST) -> bool:
    """Return True if the argument looks like a dynamically built string."""
    # f-string with at least one FormattedValue
    if isinstance(arg, ast.JoinedStr):
        return any(isinstance(v, ast.FormattedValue) for v in arg.values)
    # "..." + var  /  var + "..."
    if isinstance(arg, ast.BinOp) and isinstance(arg.op, ast.Add):
        return any(
            isinstance(side, ast.Constant) and isinstance(side.value, str)
            for side in (arg.left, arg.right)
        )
    # "..." % (...)
    if isinstance(arg, ast.BinOp) and isinstance(arg.op, ast.Mod):
        if isinstance(arg.left, ast.Constant) and isinstance(arg.left.value, str):
            return True
    # "...".format(...)
    if isinstance(arg, ast.Call):
        func = arg.func
        if isinstance(func, ast.Attribute) and func.attr == "format":
            if isinstance(func.value, ast.Constant) and isinstance(
                func.value.value, str
            ):
                return True
    return False


def _has_sql_keyword(node: ast.AST) -> bool:
    for piece in _string_pieces(node):
        if SQL_KEYWORDS.search(piece):
            return True
    return False


def scan_python(source: str, origin: str, line_offset: int = 0) -> list[str]:
    findings: list[str] = []
    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        # Best-effort: skip unparseable fences silently.
        return findings
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = None
        if isinstance(func, ast.Attribute):
            name = func.attr
        elif isinstance(func, ast.Name):
            name = func.id
        if name not in EXECUTE_NAMES:
            continue
        if not node.args:
            continue
        arg0 = node.args[0]
        if _is_dynamic_sql(arg0) and _has_sql_keyword(arg0):
            line = (node.lineno or 0) + line_offset
            findings.append(
                f"{origin}:{line}: dynamic SQL passed to {name}() — "
                f"use parameterized queries (cursor.{name}(sql, params))"
            )
    return findings


def scan_markdown(text: str, origin: str) -> list[str]:
    findings: list[str] = []
    in_fence = False
    fence_lang = ""
    fence_start_line = 0
    buf: list[str] = []
    for idx, line in enumerate(text.splitlines(), start=1):
        m = FENCE_RE.match(line)
        if m:
            if not in_fence:
                in_fence = True
                fence_lang = m.group(1).lower()
                fence_start_line = idx
                buf = []
            else:
                if fence_lang in ("python", "py", "python3"):
                    findings.extend(
                        scan_python(
                            "\n".join(buf),
                            origin,
                            line_offset=fence_start_line,
                        )
                    )
                in_fence = False
                fence_lang = ""
                buf = []
            continue
        if in_fence:
            buf.append(line)
    return findings


def scan_file(path: Path) -> list[str]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        print(f"error: cannot read {path}: {e}", file=sys.stderr)
        return []
    if path.suffix in (".md", ".markdown"):
        return scan_markdown(text, str(path))
    return scan_python(text, str(path))


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: detector.py <file> [<file> ...]", file=sys.stderr)
        return 2
    all_findings: list[str] = []
    for arg in argv[1:]:
        p = Path(arg)
        if not p.exists():
            print(f"error: not found: {p}", file=sys.stderr)
            return 2
        all_findings.extend(scan_file(p))
    for f in all_findings:
        print(f)
    return 1 if all_findings else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
