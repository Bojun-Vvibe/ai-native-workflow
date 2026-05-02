#!/usr/bin/env python3
"""Detect PHP runtime configurations that ship with ``display_errors``
turned on (a.k.a. PHP error oversharing).

PHP's ``display_errors = On`` causes warnings, notices, and full stack
traces — including absolute file paths, DB hostnames, and sometimes
serialized object dumps — to be emitted directly into the HTTP response
body. In production this is both a sensitive-information disclosure
(CWE-209 / CWE-215) and a recon enabler that fingerprints framework
versions, file layouts, and env vars for downstream attacks.

LLM-generated ``php.ini``, ``.user.ini``, ``.htaccess``, Dockerfile
``RUN`` lines, and bootstrap ``index.php`` files routinely contain
shapes like::

    display_errors = On
    display_startup_errors = 1
    error_reporting = E_ALL

or::

    ini_set('display_errors', '1');
    ini_set('display_errors', 'stderr');  # acceptable
    error_reporting(E_ALL);

This detector flags the unsafe shapes while accepting:
  - ``display_errors = stderr`` (logged, not rendered to client)
  - ``display_errors = Off`` / ``0`` / ``false``
  - files containing a ``# php-display-errors-allowed`` suppression
    comment (for local dev fixtures committed on purpose).

What's checked (per file):
  - INI-style ``display_errors`` set to a truthy value
    (``On``, ``1``, ``true``, ``yes``, ``stdout``).
  - ``ini_set('display_errors', ...)`` calls with a truthy literal
    argument.
  - ``.htaccess`` ``php_flag display_errors on`` /
    ``php_value display_errors 1``.
  - Dockerfile ``RUN`` lines that ``sed`` / ``echo`` ``display_errors``
    to a truthy value.

CWE refs:
  - CWE-209: Generation of Error Message Containing Sensitive
    Information
  - CWE-215: Insertion of Sensitive Information Into Debugging Code
  - CWE-200: Exposure of Sensitive Information to an Unauthorized
    Actor

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

SUPPRESS = re.compile(r"#\s*php-display-errors-allowed", re.IGNORECASE)

TRUTHY = {"on", "1", "true", "yes", "stdout"}
SAFE = {"off", "0", "false", "no", "stderr", ""}

# INI: display_errors = On
INI_RE = re.compile(
    r"^\s*display_errors\s*=\s*([A-Za-z0-9_'\"-]+)",
    re.IGNORECASE,
)

# ini_set('display_errors', '1');  or  ini_set("display_errors", 1);
INI_SET_RE = re.compile(
    r"""ini_set\s*\(\s*['"]display_errors['"]\s*,\s*['"]?([A-Za-z0-9_-]+)['"]?\s*\)""",
    re.IGNORECASE,
)

# .htaccess
HTACCESS_FLAG_RE = re.compile(
    r"^\s*php_flag\s+display_errors\s+(\S+)", re.IGNORECASE
)
HTACCESS_VALUE_RE = re.compile(
    r"^\s*php_value\s+display_errors\s+(\S+)", re.IGNORECASE
)

# Dockerfile sed/echo into php.ini
DOCKER_SED_RE = re.compile(
    r"""sed[^\n]*display_errors\s*=\s*([A-Za-z0-9_'"-]+)""",
    re.IGNORECASE,
)
DOCKER_ECHO_RE = re.compile(
    r"""echo[^\n]*display_errors\s*=\s*([A-Za-z0-9_'"-]+)""",
    re.IGNORECASE,
)


def _normalize(val: str) -> str:
    return val.strip().strip("'\"").lower()


def _is_truthy(val: str) -> bool:
    v = _normalize(val)
    return v in TRUTHY


def scan(source: str) -> List[Tuple[int, str]]:
    findings: List[Tuple[int, str]] = []
    if SUPPRESS.search(source):
        return findings

    for i, raw in enumerate(source.splitlines(), start=1):
        line = raw.split(";", 1)[0]  # ini comments
        # Don't strip # here — htaccess comments use #, but php uses //.
        # Cheap: skip leading-comment lines for ini/htaccess only.
        stripped = raw.lstrip()
        if stripped.startswith("#") or stripped.startswith("//"):
            continue

        m = INI_RE.match(line)
        if m and _is_truthy(m.group(1)):
            findings.append((i, f"display_errors = {m.group(1)} renders errors to HTTP response"))
            continue

        m = INI_SET_RE.search(raw)
        if m and _is_truthy(m.group(1)):
            findings.append((i, f"ini_set('display_errors', {m.group(1)!r}) enables error rendering"))
            continue

        m = HTACCESS_FLAG_RE.match(raw)
        if m and _is_truthy(m.group(1)):
            findings.append((i, f".htaccess php_flag display_errors {m.group(1)} enables error rendering"))
            continue

        m = HTACCESS_VALUE_RE.match(raw)
        if m and _is_truthy(m.group(1)):
            findings.append((i, f".htaccess php_value display_errors {m.group(1)} enables error rendering"))
            continue

        m = DOCKER_SED_RE.search(raw)
        if m and _is_truthy(m.group(1)):
            findings.append((i, f"Dockerfile sed sets display_errors={m.group(1)} in php.ini"))
            continue

        m = DOCKER_ECHO_RE.search(raw)
        if m and _is_truthy(m.group(1)):
            findings.append((i, f"Dockerfile echo sets display_errors={m.group(1)} in php.ini"))
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
