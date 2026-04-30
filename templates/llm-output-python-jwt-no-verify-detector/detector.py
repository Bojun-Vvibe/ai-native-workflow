#!/usr/bin/env python3
"""llm-output-python-jwt-no-verify-detector.

Pure-stdlib single-pass line scanner that flags Python source where
PyJWT's verification is suppressed via `verify=False`, an `options`
dict that disables `verify_signature`, or any encode/decode call that
asks PyJWT to operate without checking the signature.

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

# Patterns are intentionally conservative line-level regexes. The goal
# is to catch the canonical LLM-emitted footguns, not to parse Python.
_PATTERNS: List[Tuple[str, "re.Pattern[str]"]] = [
    (
        "verify=False kwarg passed to jwt decode/encode",
        re.compile(r"\bverify\s*=\s*False\b"),
    ),
    (
        'options dict disables verify_signature',
        re.compile(r"""verify_signature['"]\s*:\s*False"""),
    ),
    (
        'algorithms list contains "none"',
        re.compile(r"""algorithms\s*=\s*\[[^\]]*['"]none['"]""", re.IGNORECASE),
    ),
    (
        "algorithms=None disables algorithm allow-list",
        re.compile(r"\balgorithms\s*=\s*None\b"),
    ),
    (
        'algorithm="none" passed to jwt call',
        re.compile(r"""\balgorithm\s*=\s*['"]none['"]""", re.IGNORECASE),
    ),
    (
        "options dict disables verify_aud / verify_exp / verify_iat / verify_nbf / verify_iss",
        re.compile(
            r"""verify_(?:aud|exp|iat|nbf|iss)['"]\s*:\s*False"""
        ),
    ),
]

_OK_MARKER = "# jwt-verify-ok"


def _strip_inline_comment(line: str) -> str:
    """Drop inline `#` comments while preserving `#` characters that
    appear inside single-line string literals. Heuristic, not a full
    tokenizer; sufficient for line-level pattern matching."""
    out: List[str] = []
    in_str: str | None = None
    i = 0
    n = len(line)
    while i < n:
        ch = line[i]
        if in_str is None:
            if ch == "#":
                break
            if ch in ("'", '"'):
                in_str = ch
            out.append(ch)
            i += 1
            continue
        # inside a single-line string
        out.append(ch)
        if ch == "\\" and i + 1 < n:
            out.append(line[i + 1])
            i += 2
            continue
        if ch == in_str:
            in_str = None
        i += 1
    return "".join(out)


def _is_pure_docstring_line(line: str) -> bool:
    """A line that is only a string literal (a docstring continuation)."""
    stripped = line.strip()
    if not stripped:
        return False
    if stripped.startswith(('"""', "'''")):
        return True
    if stripped.startswith(('"', "'")) and stripped.endswith(('"', "'")):
        # quick heuristic: no assignment / call before the quote
        return True
    return False


def _iter_python_files(paths: Iterable[str]) -> Iterable[str]:
    for p in paths:
        if os.path.isdir(p):
            for root, _, files in os.walk(p):
                # skip hidden dirs (e.g. .git)
                if os.path.basename(root).startswith("."):
                    continue
                for f in files:
                    if f.endswith(".py"):
                        yield os.path.join(root, f)
        elif os.path.isfile(p):
            yield p


def scan_file(path: str) -> List[Tuple[int, str, str]]:
    findings: List[Tuple[int, str, str]] = []
    in_triple: str | None = None
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            for lineno, raw in enumerate(fh, start=1):
                # Track multi-line triple-quoted strings (docstrings).
                # If we are currently inside one, skip the line entirely
                # unless the closing delimiter appears on it.
                line_for_scan = raw
                if in_triple is not None:
                    end = raw.find(in_triple)
                    if end == -1:
                        continue
                    in_triple = None
                    line_for_scan = raw[end + 3 :]
                # Look for an opening triple-quote that does not close
                # on the same line.
                for delim in ('"""', "'''"):
                    first = line_for_scan.find(delim)
                    if first == -1:
                        continue
                    second = line_for_scan.find(delim, first + 3)
                    if second == -1:
                        in_triple = delim
                        line_for_scan = line_for_scan[:first]
                        break
                if _OK_MARKER in raw:
                    continue
                code = _strip_inline_comment(line_for_scan)
                for label, pat in _PATTERNS:
                    if pat.search(code):
                        findings.append((lineno, label, raw.rstrip("\n")))
                        break  # one finding per line is enough
    except OSError as exc:
        print(f"warn: could not read {path}: {exc}", file=sys.stderr)
    return findings


def main(argv: List[str]) -> int:
    if len(argv) < 2:
        print(__doc__ or "", file=sys.stderr)
        return 2
    total = 0
    for fpath in _iter_python_files(argv[1:]):
        for lineno, label, snippet in scan_file(fpath):
            print(f"{fpath}:{lineno}: {label}: {snippet.strip()}")
            total += 1
    return 1 if total else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
