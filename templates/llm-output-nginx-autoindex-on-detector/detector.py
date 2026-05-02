#!/usr/bin/env python3
"""Detect nginx config files that enable ``autoindex on;``.

``autoindex on;`` makes nginx render an HTML directory listing for any
directory under the matched ``location`` that lacks an ``index`` file.
That exposes the entire directory subtree to whoever can reach the
location — including ``.git``, ``.env``, backup tarballs, and stray
``id_rsa`` files. LLM-generated nginx snippets often enable it as a
"quick file share" without thinking about exposure.

What's checked (per file):
  - Any active (non-commented) ``autoindex on;`` directive at any
    scope (http / server / location).
  - ``autoindex_exact_size on;`` and ``autoindex_localtime on;`` are
    flagged only when paired with an enabling ``autoindex on;`` in the
    same file (alone they are inert).

CWE refs:
  - CWE-548: Exposure of Information Through Directory Listing
  - CWE-538: Insertion of Sensitive Information into Externally
    Accessible File or Directory
  - CWE-200: Exposure of Sensitive Information to an Unauthorized
    Actor

False-positive surface:
  - Internal-only locations behind ``allow``/``deny`` or
    ``auth_basic``. Suppress per file with a comment
    ``# nginx-autoindex-allowed`` anywhere in the file.
  - ``autoindex off;`` is fine and is the nginx default.

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

SUPPRESS = re.compile(r"#\s*nginx-autoindex-allowed")

AUTOINDEX_ON_RE = re.compile(
    r"^\s*autoindex\s+on\s*;", re.IGNORECASE
)
AUTOINDEX_EXACT_RE = re.compile(
    r"^\s*autoindex_exact_size\s+on\s*;", re.IGNORECASE
)
AUTOINDEX_LOCAL_RE = re.compile(
    r"^\s*autoindex_localtime\s+on\s*;", re.IGNORECASE
)


def _strip_comment(line: str) -> str:
    # nginx comments start with `#`. Strings can't contain `#` in the
    # contexts we care about (autoindex), so naive stripping is fine.
    return line.split("#", 1)[0]


def scan(source: str) -> List[Tuple[int, str]]:
    findings: List[Tuple[int, str]] = []
    if SUPPRESS.search(source):
        return findings

    autoindex_on_seen = False

    for i, raw in enumerate(source.splitlines(), start=1):
        body = _strip_comment(raw)
        if not body.strip():
            continue
        if AUTOINDEX_ON_RE.match(body):
            autoindex_on_seen = True
            findings.append((
                i,
                "autoindex on; exposes directory listing to anyone reaching this location",
            ))

    if autoindex_on_seen:
        for i, raw in enumerate(source.splitlines(), start=1):
            body = _strip_comment(raw)
            if not body.strip():
                continue
            if AUTOINDEX_EXACT_RE.match(body):
                findings.append((
                    i,
                    "autoindex_exact_size on; (paired with autoindex on;) leaks file sizes",
                ))
            elif AUTOINDEX_LOCAL_RE.match(body):
                findings.append((
                    i,
                    "autoindex_localtime on; (paired with autoindex on;) leaks server local time / mtime",
                ))

    return findings


def scan_paths(paths: Iterable[Path]) -> int:
    bad_files = 0
    targets: List[Path] = []
    for path in paths:
        if path.is_dir():
            for ext in ("*.conf", "nginx.conf"):
                targets.extend(sorted(path.rglob(ext)))
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
