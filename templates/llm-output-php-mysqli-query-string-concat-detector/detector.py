#!/usr/bin/env python3
"""llm-output-php-mysqli-query-string-concat-detector.

Pure-stdlib python3 line scanner that flags PHP code which passes a
non-literal SQL string into ``mysqli_query()`` /
``mysqli::query()`` / ``mysqli_real_query()`` / ``->multi_query()``,
where "non-literal" means the argument contains:

* string concatenation (``.`` operator) of variables, or
* double-quoted interpolation with ``$var`` / ``{$expr}``, or
* a heredoc with ``$`` substitutions, or
* a bare variable reference (``$sql``) that, on the same line, was
  built from concatenation/interpolation.

This is the canonical SQL-injection sink for the procedural and
object-oriented mysqli APIs. The fix is always a prepared statement
with ``mysqli_prepare()`` / ``->prepare()`` and bound parameters via
``mysqli_stmt_bind_param`` / ``->bind_param``.

LLMs reach for concatenated mysqli_query() because:

1. They were translating a "select * where id = X" sentence and the
   shortest path to working PHP is ``"SELECT * FROM t WHERE id=$id"``.
2. They saw a 2009 tutorial that used ``mysql_query`` (not even
   mysqli) and forward-ported only the function name.
3. They tried to "sanitise" with ``mysqli_real_escape_string`` and
   then concatenated, missing that prepared statements are simpler.

Detector only. Reports findings to stdout. Never executes input.

Usage:
    python3 detector.py <file-or-directory> [...]

Exit codes:
    0  no findings
    1  one or more findings
    2  usage error
"""
from __future__ import annotations

import os
import re
import sys
from typing import Iterable, List, Tuple

_OK_MARKER = "// mysqli-concat-ok"
_OK_MARKER_HASH = "# mysqli-concat-ok"

EXTS = {".php", ".phtml", ".inc"}

# Match a query call. We capture the SQL argument up to the matching
# top-level comma or the closing paren.
# We anchor on the opening paren of the call.
_CALL_PATTERNS = [
    ("mysqli_query", re.compile(r"""\bmysqli_query\s*\(""")),
    ("mysqli_real_query", re.compile(r"""\bmysqli_real_query\s*\(""")),
    ("mysqli_multi_query", re.compile(r"""\bmysqli_multi_query\s*\(""")),
    ("mysqli->query", re.compile(r"""->\s*query\s*\(""")),
    ("mysqli->real_query", re.compile(r"""->\s*real_query\s*\(""")),
    ("mysqli->multi_query", re.compile(r"""->\s*multi_query\s*\(""")),
]

# A bare single-quoted string literal: 'text' with no concatenation.
_SQ_LITERAL = re.compile(r"""^\s*'(?:\\.|[^'\\])*'\s*$""")
# A bare double-quoted string with NO $ interpolation.
_DQ_PURE = re.compile(r"""^\s*"(?:\\.|[^"\\$])*"\s*$""")
# Detects $var interpolation inside a "..." string.
_DQ_INTERP = re.compile(r"""\$[A-Za-z_]|\{\$""")


def _strip_php_line_comment(line: str) -> str:
    """Drop // and # comments outside of strings (best-effort)."""
    out: List[str] = []
    in_str: str | None = None
    i = 0
    n = len(line)
    while i < n:
        ch = line[i]
        if in_str is None:
            if ch == "/" and i + 1 < n and line[i + 1] == "/":
                break
            if ch == "#" :
                break
            if ch in ("'", '"'):
                in_str = ch
            out.append(ch)
            i += 1
            continue
        out.append(ch)
        if ch == "\\" and i + 1 < n:
            out.append(line[i + 1])
            i += 2
            continue
        if ch == in_str:
            in_str = None
        i += 1
    return "".join(out)


def _split_call_args(code: str, start: int) -> List[str]:
    """Given the index of the opening '(' of a call, return the list of
    top-level argument substrings (untrimmed). Returns [] if unbalanced
    on this line.
    """
    if start >= len(code) or code[start] != "(":
        return []
    depth = 1
    in_str: str | None = None
    i = start + 1
    arg_start = i
    n = len(code)
    args: List[str] = []
    while i < n:
        ch = code[i]
        if in_str is not None:
            if ch == "\\" and i + 1 < n:
                i += 2
                continue
            if ch == in_str:
                in_str = None
            i += 1
            continue
        if ch in ("'", '"'):
            in_str = ch
            i += 1
            continue
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                args.append(code[arg_start:i])
                return args
        elif ch == "," and depth == 1:
            args.append(code[arg_start:i])
            arg_start = i + 1
        i += 1
    return []


def _is_safe_sql_arg(arg: str) -> bool:
    s = arg.strip()
    if not s:
        return True  # nothing to evaluate
    # Bare single-quoted literal.
    if _SQ_LITERAL.match(s):
        return True
    # Bare double-quoted with NO interpolation.
    if _DQ_PURE.match(s) and not _DQ_INTERP.search(s):
        return True
    # Concatenation operator anywhere -> unsafe.
    if "." in s and re.search(r"""(?<!\\)['"]\s*\.|\.\s*['"$]""", s):
        return True if False else False  # unreachable; explicit reject below
    if re.search(r"""['"]\s*\.\s*\$|\.\s*['"]\s*\$|\$\w+\s*\.""", s):
        return False
    # Double-quoted with $ interpolation -> unsafe.
    if s.startswith('"') and _DQ_INTERP.search(s):
        return False
    # Heredoc on same line is rare; treat <<<TAG as unsafe if contains $.
    if "<<<" in s and "$" in s:
        return False
    # Bare variable like $sql -> we conservatively flag.
    if re.match(r"""^\$[A-Za-z_]\w*$""", s):
        return False
    # sprintf("... %s ...", ...) -> still injection, flag.
    if re.match(r"""^sprintf\s*\(""", s):
        return False
    # Function call producing the SQL we cannot inspect; conservative flag
    # only when it includes obvious concatenation/interpolation inside.
    if re.search(r"""\$\w+""", s):
        return False
    # Otherwise (e.g. a constant identifier QUERY_ALL_USERS) -> safe.
    return True


def _strip_block_comments_inline(line: str, in_block: bool) -> Tuple[str, bool]:
    if in_block:
        end = line.find("*/")
        if end == -1:
            return "", True
        line = line[end + 2 :]
        in_block = False
    out = []
    i = 0
    n = len(line)
    while i < n:
        if i + 1 < n and line[i] == "/" and line[i + 1] == "*":
            end = line.find("*/", i + 2)
            if end == -1:
                in_block = True
                break
            i = end + 2
            out.append(" ")
            continue
        out.append(line[i])
        i += 1
    return "".join(out), in_block


def _iter_target_files(paths: Iterable[str]) -> Iterable[str]:
    for p in paths:
        if os.path.isdir(p):
            for root, _, files in os.walk(p):
                if os.path.basename(root).startswith("."):
                    continue
                for f in files:
                    if os.path.splitext(f)[1] in EXTS:
                        yield os.path.join(root, f)
        elif os.path.isfile(p):
            yield p


def scan_file(path: str) -> List[Tuple[int, str, str]]:
    findings: List[Tuple[int, str, str]] = []
    in_block = False
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            for lineno, raw in enumerate(fh, start=1):
                if _OK_MARKER in raw or _OK_MARKER_HASH in raw:
                    continue
                stripped, in_block = _strip_block_comments_inline(raw, in_block)
                code = _strip_php_line_comment(stripped)

                hit = False
                for label, pat in _CALL_PATTERNS:
                    if hit:
                        break
                    for m in pat.finditer(code):
                        paren = m.end() - 1
                        args = _split_call_args(code, paren)
                        if not args:
                            continue
                        # Procedural mysqli_*: first arg is link, SQL is #2.
                        # OO ->query/->real_query/->multi_query: SQL is #1.
                        if label.startswith("mysqli_"):
                            if len(args) < 2:
                                continue
                            target = args[1]
                        else:
                            target = args[0]
                        if not _is_safe_sql_arg(target):
                            findings.append(
                                (
                                    lineno,
                                    f"{label}() with non-literal SQL",
                                    raw.rstrip("\n"),
                                )
                            )
                            hit = True
                            break
    except OSError as exc:
        print(f"warn: could not read {path}: {exc}", file=sys.stderr)
    return findings


def main(argv: List[str]) -> int:
    if len(argv) < 2:
        print(__doc__ or "", file=sys.stderr)
        return 2
    total = 0
    for fpath in _iter_target_files(argv[1:]):
        for lineno, label, snippet in scan_file(fpath):
            print(f"{fpath}:{lineno}: {label}: {snippet.strip()}")
            total += 1
    return 1 if total else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
