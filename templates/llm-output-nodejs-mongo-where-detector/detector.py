#!/usr/bin/env python3
"""llm-output-nodejs-mongo-where-detector.

Pure-stdlib python3 line scanner that flags Node.js code which
passes a non-literal value as the MongoDB ``$where`` operator (or
calls the deprecated ``Collection.$where`` / ``db.eval`` /
``mapReduce`` with a non-literal function body).

MongoDB's ``$where`` operator runs a JavaScript expression on the
server. If the value of ``$where`` is a string built from request
input, the attacker can inject arbitrary JS and run it inside the
mongod process. ``mapReduce`` and ``db.eval`` have the same shape.

LLMs reach for ``$where`` because:

1. The user said "find docs where this complex condition holds" and
   ``$where`` is the answer the model memorised from a 2014 blog post.
2. The model translated a SQL ``WHERE`` clause literally.
3. The model wanted to use a regex but did not remember ``$regex``.

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

_OK_MARKER = "// mongo-where-ok"

EXTS = {".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx"}

# Match `$where: <value>` or `"$where": <value>` or `'$where': <value>`
# inside an object literal. We capture the value text up to the next
# comma / closing brace / end of line, then decide whether it is a
# bare string / function literal.
_WHERE_PROP = re.compile(
    r"""(?P<key>(?:"\$where"|'\$where'|\$where))\s*:\s*(?P<val>.+?)(?=,|\}|$)""",
    re.MULTILINE,
)

# Direct call: `coll.$where(<expr>)` (legacy mongoose helper).
_WHERE_METHOD = re.compile(r"""\.\s*\$where\s*\(\s*(?P<arg>[^)]*)\)""")

# `db.eval(<expr>)` - deprecated, runs JS on server.
_DB_EVAL = re.compile(r"""\bdb\s*\.\s*eval\s*\(\s*(?P<arg>[^)]*)\)""")

# `coll.mapReduce(<map>, ...)` first arg as JS function body string.
_MAP_REDUCE = re.compile(r"""\.\s*mapReduce\s*\(\s*(?P<arg>[^,)]*)""")

# A "bare" string literal value: 'x' or "x" with no template / concat /
# var. We keep this conservative — anything starting with `var`-like
# token is non-literal.
_BARE_QSTRING = re.compile(r"""^\s*(?P<q>'|")(?:(?!(?P=q)).)*(?P=q)\s*$""")
# A bare template literal with NO ${...} substitutions.
_BARE_TEMPLATE = re.compile(r"""^\s*`(?:(?!\$\{)[^`])*`\s*$""")
# A function literal: `function (...) { ... }` or arrow `(...) => ...`
# with NO ${} interpolation and NO + concatenation visible.
_FUNCTION_LITERAL = re.compile(
    r"""^\s*(?:function\s*\([^)]*\)\s*\{.*\}|\([^)]*\)\s*=>\s*[^+]+)\s*$""",
    re.DOTALL,
)


def _looks_literal(value: str) -> bool:
    v = value.strip()
    if not v:
        return False
    if "${" in v:
        return False  # template interpolation
    if " + " in v or "+ " in v[:64]:
        return False  # concatenation
    if _BARE_QSTRING.match(v):
        return True
    if _BARE_TEMPLATE.match(v):
        return True
    if _FUNCTION_LITERAL.match(v):
        return True
    return False


def _strip_line_comment(line: str) -> str:
    """Drop // comments outside of strings (best-effort)."""
    out: List[str] = []
    in_str: str | None = None
    i = 0
    n = len(line)
    while i < n:
        ch = line[i]
        if in_str is None:
            if ch == "/" and i + 1 < n and line[i + 1] == "/":
                break
            if ch in ("'", '"', "`"):
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
    in_block_comment = False
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            for lineno, raw in enumerate(fh, start=1):
                if _OK_MARKER in raw:
                    continue
                line = raw

                # Track /* ... */ block comments line-by-line.
                if in_block_comment:
                    end = line.find("*/")
                    if end == -1:
                        continue
                    line = line[end + 2 :]
                    in_block_comment = False
                while True:
                    start = line.find("/*")
                    if start == -1:
                        break
                    end = line.find("*/", start + 2)
                    if end == -1:
                        in_block_comment = True
                        line = line[:start]
                        break
                    line = line[:start] + " " * (end + 2 - start) + line[end + 2 :]

                code = _strip_line_comment(line)

                for m in _WHERE_PROP.finditer(code):
                    val = m.group("val")
                    if _looks_literal(val):
                        continue
                    findings.append(
                        (
                            lineno,
                            "$where operator with non-literal value",
                            raw.rstrip("\n"),
                        )
                    )
                    break

                m = _WHERE_METHOD.search(code)
                if m and not _looks_literal(m.group("arg")):
                    findings.append(
                        (
                            lineno,
                            "Collection.$where() with non-literal argument",
                            raw.rstrip("\n"),
                        )
                    )

                m = _DB_EVAL.search(code)
                if m and not _looks_literal(m.group("arg")):
                    findings.append(
                        (
                            lineno,
                            "db.eval() with non-literal argument",
                            raw.rstrip("\n"),
                        )
                    )

                m = _MAP_REDUCE.search(code)
                if m:
                    arg = m.group("arg").strip()
                    # Reject only if arg is a quoted/template string with
                    # interpolation/concatenation (i.e. JS-as-string built
                    # from input). A function reference like `mapFn` is
                    # considered safe at this layer.
                    is_string_arg = arg.startswith(("'", '"', "`"))
                    if is_string_arg and not _looks_literal(arg):
                        findings.append(
                            (
                                lineno,
                                "mapReduce() with non-literal JS string",
                                raw.rstrip("\n"),
                            )
                        )
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
