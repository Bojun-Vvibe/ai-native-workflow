#!/usr/bin/env python3
"""Detect PHP runtime configurations that enable ``allow_url_include``.

PHP's ``allow_url_include = On`` makes ``include`` / ``require`` /
``include_once`` / ``require_once`` accept URL wrappers
(``http://``, ``https://``, ``ftp://``, ``data://``, ``php://``, ...)
as the path argument. When combined with even a single tainted include
target this is a one-shot Remote File Inclusion (RFI) primitive that
fetches and executes attacker-controlled PHP from a remote origin
(CWE-98 / CWE-94). PHP itself ships with this disabled for a reason.

LLM-generated ``php.ini``, ``.user.ini``, ``.htaccess``, Dockerfile
``RUN`` lines, and bootstrap PHP files routinely contain shapes like::

    allow_url_include = On
    allow_url_fopen = 1

or::

    ini_set('allow_url_include', '1');
    ini_set('allow_url_include', 'true');

This detector flags those shapes. ``allow_url_fopen`` is *not* flagged
on its own (it has legitimate uses for file_get_contents); only
``allow_url_include`` is treated as the RFI smoking gun.

What's checked (per file):
  - INI-style ``allow_url_include`` set to a truthy value
    (``On``, ``1``, ``true``, ``yes``).
  - ``ini_set('allow_url_include', ...)`` calls with a truthy literal.
  - ``.htaccess`` ``php_flag allow_url_include on`` /
    ``php_value allow_url_include 1``.
  - Dockerfile ``RUN`` lines that ``sed`` / ``echo``
    ``allow_url_include`` to a truthy value.

Accepted:
  - ``allow_url_include = Off`` / ``0`` / ``false``.
  - Files containing ``# php-allow-url-include-allowed`` are skipped
    wholesale (e.g. legacy compatibility fixtures).

CWE refs:
  - CWE-98: Improper Control of Filename for Include/Require Statement
    in PHP Program ('PHP Remote File Inclusion')
  - CWE-94: Improper Control of Generation of Code ('Code Injection')
  - CWE-829: Inclusion of Functionality from Untrusted Control Sphere

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

SUPPRESS = re.compile(r"#\s*php-allow-url-include-allowed", re.IGNORECASE)

TRUTHY = {"on", "1", "true", "yes"}

INI_RE = re.compile(
    r"^\s*allow_url_include\s*=\s*([A-Za-z0-9_'\"-]+)",
    re.IGNORECASE,
)

INI_SET_RE = re.compile(
    r"""ini_set\s*\(\s*['"]allow_url_include['"]\s*,\s*['"]?([A-Za-z0-9_-]+)['"]?\s*\)""",
    re.IGNORECASE,
)

HTACCESS_FLAG_RE = re.compile(
    r"^\s*php_flag\s+allow_url_include\s+(\S+)", re.IGNORECASE
)
HTACCESS_VALUE_RE = re.compile(
    r"^\s*php_value\s+allow_url_include\s+(\S+)", re.IGNORECASE
)

DOCKER_SED_RE = re.compile(
    r"""sed[^\n]*allow_url_include\s*=\s*([A-Za-z0-9_'"-]+)""",
    re.IGNORECASE,
)
DOCKER_ECHO_RE = re.compile(
    r"""echo[^\n]*allow_url_include\s*=\s*([A-Za-z0-9_'"-]+)""",
    re.IGNORECASE,
)


def _normalize(val: str) -> str:
    return val.strip().strip("'\"").lower()


def _is_truthy(val: str) -> bool:
    return _normalize(val) in TRUTHY


def scan(source: str) -> List[Tuple[int, str]]:
    findings: List[Tuple[int, str]] = []
    if SUPPRESS.search(source):
        return findings

    for i, raw in enumerate(source.splitlines(), start=1):
        line = raw.split(";", 1)[0]  # ini comments
        stripped = raw.lstrip()
        if stripped.startswith("#") or stripped.startswith("//"):
            continue

        m = INI_RE.match(line)
        if m and _is_truthy(m.group(1)):
            findings.append(
                (i, f"allow_url_include = {m.group(1)} enables PHP Remote File Inclusion")
            )
            continue

        m = INI_SET_RE.search(raw)
        if m and _is_truthy(m.group(1)):
            findings.append(
                (i, f"ini_set('allow_url_include', {m.group(1)!r}) enables PHP RFI")
            )
            continue

        m = HTACCESS_FLAG_RE.match(raw)
        if m and _is_truthy(m.group(1)):
            findings.append(
                (i, f".htaccess php_flag allow_url_include {m.group(1)} enables PHP RFI")
            )
            continue

        m = HTACCESS_VALUE_RE.match(raw)
        if m and _is_truthy(m.group(1)):
            findings.append(
                (i, f".htaccess php_value allow_url_include {m.group(1)} enables PHP RFI")
            )
            continue

        m = DOCKER_SED_RE.search(raw)
        if m and _is_truthy(m.group(1)):
            findings.append(
                (i, f"Dockerfile sed sets allow_url_include={m.group(1)} in php.ini")
            )
            continue

        m = DOCKER_ECHO_RE.search(raw)
        if m and _is_truthy(m.group(1)):
            findings.append(
                (i, f"Dockerfile echo sets allow_url_include={m.group(1)} in php.ini")
            )
            continue

    return findings


def scan_paths(paths: Iterable[Path]) -> int:
    bad_files = 0
    targets: List[Path] = []
    for path in paths:
        if path.is_dir():
            for pat in ("*.ini", "*.htaccess", "Dockerfile*", "*.php"):
                targets.extend(sorted(path.rglob(pat)))
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
