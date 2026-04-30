#!/usr/bin/env python3
"""Detect Python source that calls ``eval()``, ``exec()``, or ``compile()`` on
data that is not a literal string. LLM-generated code routinely reaches for
``eval`` / ``exec`` to "parse" config, evaluate user-supplied math, or
dispatch on a string from a request — every one of those is a remote code
execution bug.

What this flags
---------------
- ``eval(x)`` / ``exec(x)`` / ``compile(x, ...)`` where the first argument is
  not a constant string literal (i.e. anything dynamic)
- ``eval(f"...")``, ``eval("a" + b)``, ``eval(some_var)``
- ``__builtins__.eval(...)`` and ``builtins.eval(...)`` access patterns

What it does not flag
---------------------
- ``eval("1 + 2")`` with a constant-string literal argument (still
  discouraged, but not the dangerous pattern this rule targets)
- ``ast.literal_eval(...)`` — that is the safe replacement and is explicitly
  allowed.

Usage
-----
    python3 detector.py <path> [<path> ...]

Exit code is the number of files that contain at least one finding (capped at
255). Stdout lists ``<file>:<line>:<reason>`` for every match.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path
from typing import Iterable, List, Tuple

DANGEROUS_NAMES = {"eval", "exec", "compile"}


def _callee_name(func: ast.expr) -> str | None:
    """Return the bare callee name for ``eval``, ``exec``, ``compile`` even
    when accessed via ``builtins.eval`` / ``__builtins__.eval``."""
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        # builtins.eval / __builtins__.eval
        if isinstance(func.value, ast.Name) and func.value.id in {
            "builtins",
            "__builtins__",
        }:
            return func.attr
    return None


def _is_constant_string(node: ast.expr) -> bool:
    return isinstance(node, ast.Constant) and isinstance(node.value, str)


def scan_source(source: str) -> List[Tuple[int, str]]:
    findings: List[Tuple[int, str]] = []
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return [(exc.lineno or 0, f"syntax-error: {exc.msg}")]

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = _callee_name(node.func)
        if name not in DANGEROUS_NAMES:
            continue
        if not node.args:
            # eval() with no args is a SyntaxError at runtime; flag anyway.
            findings.append((node.lineno, f"{name}() called with no arguments"))
            continue
        first = node.args[0]
        if _is_constant_string(first):
            # constant literal: not the dynamic-RCE pattern we target
            continue
        # Anything else (Name, JoinedStr/f-string, BinOp, Call, Subscript...)
        # is a dynamic value and is unsafe.
        kind = type(first).__name__
        findings.append(
            (node.lineno, f"{name}() called with non-literal argument ({kind})")
        )
    return findings


def scan_paths(paths: Iterable[Path]) -> int:
    bad_files = 0
    for path in paths:
        if path.is_dir():
            files = sorted(path.rglob("*.py"))
        else:
            files = [path]
        for f in files:
            try:
                source = f.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as exc:
                print(f"{f}:0:read-error: {exc}")
                continue
            hits = scan_source(source)
            if hits:
                bad_files += 1
                for line, reason in hits:
                    print(f"{f}:{line}:{reason}")
    return bad_files


def main(argv: List[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 0
    paths = [Path(a) for a in argv[1:]]
    return min(255, scan_paths(paths))


if __name__ == "__main__":
    sys.exit(main(sys.argv))
