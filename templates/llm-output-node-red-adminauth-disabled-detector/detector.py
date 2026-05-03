#!/usr/bin/env python3
"""Detect Node-RED ``settings.js`` files that expose the admin
editor without authentication.

Node-RED's flow editor and admin HTTP API are protected by an
optional ``adminAuth`` block in ``settings.js``. When that block
is absent (or is present but commented out), the editor and
``/settings``, ``/flows``, ``/admin`` HTTP endpoints are reachable
by any anonymous client on the bind interface. Because Node-RED
flows can include ``function`` nodes that execute arbitrary
JavaScript inside the runtime, an unauthenticated editor is a
remote-code-execution surface (CWE-306, CWE-862).

LLM-generated quickstart ``settings.js`` files routinely ship a
``module.exports = { ... }`` block with the ``adminAuth`` example
left commented out, e.g.::

    module.exports = {
        uiPort: process.env.PORT || 1880,
        // adminAuth: {
        //     type: "credentials",
        //     users: [{ username: "admin", password: "...", permissions: "*" }]
        // },
        ...
    };

What's checked (per ``settings.js`` / ``settings.cjs`` /
``settings.mjs`` file):
  - The file contains a ``module.exports`` (or ``export default``)
    object literal.
  - That object does NOT contain an active (non-commented)
    ``adminAuth`` key.

A line is considered "active" if, after stripping leading
whitespace, it does NOT start with ``//`` and is not inside a
``/* ... */`` block comment.

Accepted (not flagged):
  - Files whose active source contains an ``adminAuth:`` key
    (regardless of value — value validity is out of scope here).
  - Files containing the marker comment
    ``// node-red-adminauth-disabled-allowed`` (skipped wholesale,
    intended for local-only smoke fixtures).
  - Files that do not look like a Node-RED settings module
    (no ``module.exports`` / ``export default`` and no
    ``uiPort`` / ``httpAdminRoot`` / ``flowFile`` / ``functionGlobalContext``
    hint) — these are skipped to keep the false-positive surface
    tight.

CWE refs:
  - CWE-306: Missing Authentication for Critical Function
  - CWE-862: Missing Authorization
  - CWE-1188: Insecure Default Initialization of Resource

Usage:
    python3 detector.py <path> [<path> ...]

Exit code: number of files with at least one finding (capped at 255).
Stdout:    ``<file>:<line>:<reason>``.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Iterable, List, Tuple

SUPPRESS = re.compile(r"//\s*node-red-adminauth-disabled-allowed", re.IGNORECASE)

# Hints that this file is in fact a Node-RED settings module.
HINTS = (
    "module.exports",
    "export default",
    "uiPort",
    "httpAdminRoot",
    "flowFile",
    "functionGlobalContext",
)

ADMIN_AUTH_KEY = re.compile(r"\badminAuth\s*:")


def _strip_block_comments(source: str) -> str:
    """Remove /* ... */ block comments. Preserves line count by
    replacing each removed character with the same character if it
    is a newline, else a space."""
    out = []
    i = 0
    n = len(source)
    in_block = False
    while i < n:
        if not in_block and i + 1 < n and source[i] == "/" and source[i + 1] == "*":
            in_block = True
            out.append("  ")
            i += 2
            continue
        if in_block and i + 1 < n and source[i] == "*" and source[i + 1] == "/":
            in_block = False
            out.append("  ")
            i += 2
            continue
        if in_block:
            out.append("\n" if source[i] == "\n" else " ")
        else:
            out.append(source[i])
        i += 1
    return "".join(out)


def _active_lines(source: str) -> List[Tuple[int, str]]:
    """Return (lineno, content) for lines whose first non-space
    chars are not ``//``. Block comments are stripped first."""
    cleaned = _strip_block_comments(source)
    out: List[Tuple[int, str]] = []
    for idx, raw in enumerate(cleaned.splitlines(), start=1):
        stripped = raw.lstrip()
        if stripped.startswith("//"):
            continue
        out.append((idx, raw))
    return out


def scan(source: str) -> List[Tuple[int, str]]:
    if SUPPRESS.search(source):
        return []
    if not any(h in source for h in HINTS):
        return []  # not a Node-RED settings module

    active = _active_lines(source)
    active_text = "\n".join(line for _, line in active)

    # Need to look like a settings export to apply this rule.
    if (
        "module.exports" not in active_text
        and "export default" not in active_text
    ):
        return []

    if ADMIN_AUTH_KEY.search(active_text):
        return []

    # Find the module.exports / export default line to anchor the finding.
    anchor_line = 1
    for lineno, content in active:
        if "module.exports" in content or "export default" in content:
            anchor_line = lineno
            break

    return [
        (
            anchor_line,
            "Node-RED settings export has no active adminAuth: "
            "editor/admin API will be reachable anonymously",
        )
    ]


def _is_target(path: Path) -> bool:
    name = path.name.lower()
    return name in {"settings.js", "settings.cjs", "settings.mjs"}


def scan_paths(paths: Iterable[Path]) -> int:
    bad_files = 0
    targets: List[Path] = []
    for path in paths:
        if path.is_dir():
            for f in sorted(path.rglob("*")):
                if f.is_file() and _is_target(f):
                    targets.append(f)
        else:
            targets.append(path)
    for f in targets:
        try:
            source = f.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            print(f"{f}:0:read-error: {exc}")
            continue
        hits = scan(source)
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
