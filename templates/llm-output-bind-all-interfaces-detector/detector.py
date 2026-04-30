#!/usr/bin/env python3
"""Detect Python source that binds a network listener to *all* interfaces
(``0.0.0.0`` or ``::`` / ``::0``). LLM-generated server scaffolds default to
``host="0.0.0.0"`` because that is what tutorials show, which silently exposes
dev / admin endpoints to every network the box touches.

What this flags
---------------
- ``socket.bind(("0.0.0.0", port))`` and ``socket.bind(("::", port))``
- Common framework run() / serve() calls with ``host="0.0.0.0"`` keyword:
  Flask ``app.run(host="0.0.0.0")``, FastAPI/uvicorn ``uvicorn.run(app, host="0.0.0.0")``,
  Django ``runserver("0.0.0.0:8000")``, ``HTTPServer(("0.0.0.0", 8000), ...)``
- The same pattern with the wildcard supplied as a positional argument when
  the call shape is unambiguous (``HTTPServer``, ``socket.bind``).

What it does not flag
---------------------
- Loopback binds (``127.0.0.1``, ``localhost``, ``::1``)
- Env-driven hosts (``host=os.environ["HOST"]``) — that is the safe escape
  hatch this rule wants people to use.
- String literals that merely *contain* ``0.0.0.0`` outside of a call (docs,
  comments, log messages) — this is AST-based and only fires on real calls.

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
from typing import Iterable, List, Optional, Tuple

WILDCARD_HOSTS = {"0.0.0.0", "::", "::0", "0:0:0:0:0:0:0:0"}

# Calls whose first positional arg is a (host, port) tuple — e.g.
# socket.bind, HTTPServer, ThreadingHTTPServer, ThreadingTCPServer …
TUPLE_BIND_CALLS = {
    "bind",
    "HTTPServer",
    "ThreadingHTTPServer",
    "TCPServer",
    "ThreadingTCPServer",
    "UDPServer",
    "ThreadingUDPServer",
}

# Calls that take the host as a ``host=`` keyword (Flask, uvicorn, hypercorn,
# aiohttp web.run_app, …) or as the first positional string.
HOST_KW_CALLS = {
    "run",
    "run_app",
    "serve",
    "create_server",
    "runserver",
}


def _attr_or_name(func: ast.expr) -> Optional[str]:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _str_const(node: ast.expr) -> Optional[str]:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _is_wildcard(value: str) -> bool:
    return value.strip() in WILDCARD_HOSTS or value.strip().startswith("0.0.0.0:")


def _check_tuple_first_arg(node: ast.Call) -> Optional[str]:
    """For socket.bind / HTTPServer-style calls: first positional arg is a
    (host, port) tuple."""
    if not node.args:
        return None
    first = node.args[0]
    if not isinstance(first, ast.Tuple) or not first.elts:
        return None
    host_node = first.elts[0]
    host = _str_const(host_node)
    if host and _is_wildcard(host):
        return f"binds to wildcard host {host!r}"
    return None


def _check_host_kw(node: ast.Call) -> Optional[str]:
    for kw in node.keywords:
        if kw.arg == "host":
            host = _str_const(kw.value)
            if host and _is_wildcard(host):
                return f"host={host!r} binds to all interfaces"
    return None


def _check_runserver_positional(node: ast.Call) -> Optional[str]:
    """Django-style ``runserver("0.0.0.0:8000")``."""
    if not node.args:
        return None
    host = _str_const(node.args[0])
    if host and _is_wildcard(host):
        return f"runserver bound to wildcard {host!r}"
    return None


def scan_source(source: str) -> List[Tuple[int, str]]:
    findings: List[Tuple[int, str]] = []
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return [(exc.lineno or 0, f"syntax-error: {exc.msg}")]

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = _attr_or_name(node.func)
        if name is None:
            continue

        if name in TUPLE_BIND_CALLS:
            reason = _check_tuple_first_arg(node)
            if reason:
                findings.append((node.lineno, f"{name}(): {reason}"))
                continue

        if name in HOST_KW_CALLS:
            reason = _check_host_kw(node)
            if reason:
                findings.append((node.lineno, f"{name}(): {reason}"))
                continue
            if name == "runserver":
                reason = _check_runserver_positional(node)
                if reason:
                    findings.append((node.lineno, f"{name}(): {reason}"))
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
