#!/usr/bin/env python3
"""Detect Django settings modules that ship ``DEBUG = True`` to
production.

LLMs asked to "give me a Django settings file" almost always emit::

    DEBUG = True
    ALLOWED_HOSTS = ['*']

That's the literal first line of `django-admin startproject`'s
generated ``settings.py``, and it is the most common Django
misconfiguration leaking stack traces, environment variables, and
SQL fragments to the public internet via the yellow debug error
page.

What's flagged
--------------
Per file, line-level findings for any of:

* ``DEBUG = True`` (any whitespace, any case on the True-literal:
  ``True``, ``1`` when assigned to ``DEBUG``).
* ``DEBUG: bool = True`` / ``DEBUG:bool=True`` annotated form.
* ``ALLOWED_HOSTS = ['*']`` / ``ALLOWED_HOSTS = ["*"]`` /
  ``ALLOWED_HOSTS = ('*',)`` — wildcard host whitelist, which makes
  the DEBUG page reachable from any Host header.
* ``TEMPLATE_DEBUG = True`` (legacy Django <1.8 setting still
  emitted by older training data).

Whole-file finding (line 0):

* The file's name suggests a production settings module
  (``settings_prod*``, ``production*``, ``prod_settings*``,
  ``settings/production.py``, ``settings/prod.py``) AND it sets
  ``DEBUG = True`` anywhere AND it does NOT read DEBUG from an env
  var (``os.environ`` / ``os.getenv`` / ``env(`` / ``config(``).

What's NOT flagged
------------------
* ``DEBUG = False``.
* ``DEBUG = os.environ.get('DJANGO_DEBUG') == '1'`` — env-driven.
* ``DEBUG = config('DEBUG', default=False, cast=bool)`` — django-environ.
* ``ALLOWED_HOSTS = ['example.com']`` — explicit hosts.
* Lines with a trailing ``# dj-debug-ok`` comment.
* Files containing ``dj-debug-ok-file`` in any comment.

Refs
----
* CWE-489: Active Debug Code
* CWE-209: Generation of Error Message Containing Sensitive Information
* OWASP Top 10 (2021) A05: Security Misconfiguration
* Django docs — "Deployment checklist" (``DEBUG`` must be False)

Usage
-----
    python3 detector.py <file_or_dir> [...]

Exit code: number of files with at least one finding (capped at 255).
Stdout:    ``<file>:<line>:<reason>``.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Iterable, List, Tuple

SUPPRESS_LINE = re.compile(r"#\s*dj-debug-ok\b")
SUPPRESS_FILE = re.compile(r"dj-debug-ok-file\b")

# DEBUG = True   |  DEBUG=True  |  DEBUG : bool = True  |  DEBUG = 1
DEBUG_TRUE = re.compile(
    r"^\s*DEBUG\s*(?::\s*bool\s*)?=\s*(?:True|1)\s*(?:#.*)?$",
)
TEMPLATE_DEBUG_TRUE = re.compile(
    r"^\s*TEMPLATE_DEBUG\s*(?::\s*bool\s*)?=\s*(?:True|1)\s*(?:#.*)?$",
)
ALLOWED_HOSTS_WILDCARD = re.compile(
    r"^\s*ALLOWED_HOSTS\s*(?::\s*[^=]+)?=\s*[\(\[]\s*['\"]\*['\"]\s*,?\s*[\)\]]\s*(?:#.*)?$",
)

ENV_DRIVEN = re.compile(
    r"(?:os\.environ|os\.getenv|environ\.get|env\s*\(|config\s*\()",
)
PROD_NAME = re.compile(
    r"(?:settings_prod|prod_settings|production|prod\.py$|prod_\w+\.py$)",
    re.IGNORECASE,
)


def scan(source: str, path: Path) -> List[Tuple[int, str]]:
    findings: List[Tuple[int, str]] = []
    if SUPPRESS_FILE.search(source):
        return findings

    debug_true_seen = False
    file_has_env = bool(ENV_DRIVEN.search(source))

    for i, raw in enumerate(source.splitlines(), start=1):
        if SUPPRESS_LINE.search(raw):
            continue

        if DEBUG_TRUE.match(raw):
            findings.append((i, "Django `DEBUG = True` in settings"))
            debug_true_seen = True
            continue

        if TEMPLATE_DEBUG_TRUE.match(raw):
            findings.append((i, "Django `TEMPLATE_DEBUG = True` (legacy debug toggle)"))
            debug_true_seen = True
            continue

        if ALLOWED_HOSTS_WILDCARD.match(raw):
            findings.append((
                i,
                "`ALLOWED_HOSTS = ['*']` accepts any Host header (debug page reachable)",
            ))
            continue

    is_prod_named = bool(PROD_NAME.search(path.name)) or "production" in str(path).lower()
    if is_prod_named and debug_true_seen and not file_has_env:
        findings.append((
            0,
            "production-named settings module hardcodes DEBUG without reading any env var",
        ))

    return findings


def _iter_files(path: Path) -> Iterable[Path]:
    if path.is_file():
        yield path
        return
    seen = set()
    for pattern in ("settings.py", "settings_*.py", "*settings*.py", "production.py", "prod.py"):
        for sub in sorted(path.rglob(pattern)):
            if sub.is_file() and sub not in seen:
                seen.add(sub)
                yield sub


def scan_paths(paths: Iterable[Path]) -> int:
    bad_files = 0
    for root in paths:
        for f in _iter_files(root):
            try:
                source = f.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as exc:
                print(f"{f}:0:read-error: {exc}")
                continue
            hits = scan(source, f)
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
