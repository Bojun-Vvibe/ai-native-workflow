#!/usr/bin/env python3
"""Detect Python source that calls the `requests` library with TLS verification
disabled (``verify=False``) or that calls ``urllib3.disable_warnings`` to
silence the resulting insecure-request warnings.

This is a defensive lint pattern. Disabling TLS verification removes the
guarantee that the server certificate chains to a trusted root, so any code
review or CI pipeline scanning LLM-generated Python should flag it before the
code lands in a real project.

Usage:
    python3 detector.py <path> [<path> ...]

Exit code is the number of files that contain at least one finding (capped at
255). Stdout lists ``<file>:<line>:<reason>`` for every match.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path
from typing import Iterable, List, Tuple

REQUESTS_METHODS = {
    "get", "post", "put", "delete", "patch", "head", "options", "request",
}


def _is_requests_call(node: ast.Call) -> bool:
    """Return True when the call looks like a `requests.<method>(...)` call."""
    func = node.func
    if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
        if func.value.id == "requests" and func.attr in REQUESTS_METHODS:
            return True
    # Session-style: `s.get(...)` is harder to attribute statically; we only
    # flag the explicit `requests.<method>` form to keep false positives low.
    return False


def _is_disable_warnings(node: ast.Call) -> bool:
    func = node.func
    if isinstance(func, ast.Attribute) and func.attr == "disable_warnings":
        if isinstance(func.value, ast.Name) and func.value.id == "urllib3":
            return True
        if isinstance(func.value, ast.Attribute) and func.value.attr == "urllib3":
            return True
    return False


def _verify_false(node: ast.Call) -> bool:
    for kw in node.keywords:
        if kw.arg == "verify" and isinstance(kw.value, ast.Constant) and kw.value.value is False:
            return True
    return False


def scan_source(source: str) -> List[Tuple[int, str]]:
    findings: List[Tuple[int, str]] = []
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return [(exc.lineno or 0, f"syntax-error: {exc.msg}")]

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if _is_requests_call(node) and _verify_false(node):
            findings.append((node.lineno, "requests call with verify=False"))
        elif _is_disable_warnings(node):
            findings.append((node.lineno, "urllib3.disable_warnings() suppresses TLS warnings"))
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
