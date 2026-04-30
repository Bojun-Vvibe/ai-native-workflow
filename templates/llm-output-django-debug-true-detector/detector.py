#!/usr/bin/env python3
"""Detect Django settings modules that ship with debug-friendly defaults that
are unsafe for any non-local environment:

  - ``DEBUG = True``
  - ``ALLOWED_HOSTS = ['*']`` (or any list/tuple containing the bare ``"*"``)
  - ``SECRET_KEY`` set to an obvious placeholder literal

This is a defensive lint pattern. LLM-generated Django settings frequently
keep the development defaults from ``django-admin startproject`` even when the
file is named ``settings_prod.py``; a CI lint step can catch it before deploy.

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

PLACEHOLDER_SECRETS = {
    "changeme",
    "change-me",
    "secret",
    "secretkey",
    "secret-key",
    "django-insecure",
    "replace-me",
    "your-secret-key",
}


def _targets(node: ast.Assign) -> List[str]:
    names: List[str] = []
    for target in node.targets:
        if isinstance(target, ast.Name):
            names.append(target.id)
    return names


def _is_star_host(value: ast.expr) -> bool:
    if not isinstance(value, (ast.List, ast.Tuple)):
        return False
    for elt in value.elts:
        if isinstance(elt, ast.Constant) and elt.value == "*":
            return True
    return False


def _is_placeholder_secret(value: ast.expr) -> bool:
    if not isinstance(value, ast.Constant) or not isinstance(value.value, str):
        return False
    text = value.value.strip().lower()
    if not text:
        return True
    if len(text) < 16:
        return True
    for marker in PLACEHOLDER_SECRETS:
        if marker in text:
            return True
    return False


def scan_source(source: str) -> List[Tuple[int, str]]:
    findings: List[Tuple[int, str]] = []
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return [(exc.lineno or 0, f"syntax-error: {exc.msg}")]

    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        names = _targets(node)
        if not names:
            continue
        for name in names:
            if name == "DEBUG" and isinstance(node.value, ast.Constant) and node.value.value is True:
                findings.append((node.lineno, "DEBUG = True in settings module"))
            elif name == "ALLOWED_HOSTS" and _is_star_host(node.value):
                findings.append((node.lineno, "ALLOWED_HOSTS contains wildcard '*'"))
            elif name == "SECRET_KEY" and _is_placeholder_secret(node.value):
                findings.append((node.lineno, "SECRET_KEY looks like a placeholder literal"))
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
