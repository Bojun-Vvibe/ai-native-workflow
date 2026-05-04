#!/usr/bin/env python3
"""Detect WordPress ``wp-config.php`` snippets that turn on
``WP_DEBUG_DISPLAY`` (or leave it at its default-on state while
``WP_DEBUG`` is enabled) without redirecting errors to a log.

WordPress exposes three related debug constants in ``wp-config.php``:

  - ``WP_DEBUG``           — master switch for verbose error output.
  - ``WP_DEBUG_DISPLAY``   — controls whether errors are rendered
                             into the HTML response sent to clients.
                             Defaults to ``true`` when ``WP_DEBUG``
                             is on but unset.
  - ``WP_DEBUG_LOG``       — sends errors to ``wp-content/debug.log``
                             instead of (or in addition to) the page.

When ``WP_DEBUG_DISPLAY`` is ``true`` on a public site, every PHP
notice / warning / fatal is printed inline and frequently leaks:

  - Absolute filesystem paths (``/var/www/html/wp-content/...``).
  - Database table prefixes and SQL fragments containing user data.
  - Stack traces revealing installed plugin/theme versions, useful
    for chaining a known-CVE exploit.
  - In bad-plugin scenarios: dumped option rows that include API
    tokens, SMTP passwords, or third-party secrets.

This is the textbook WSTG-CONF-08 / CWE-209 (Information Exposure
Through an Error Message) finding, and it shows up constantly in
LLM-suggested ``wp-config.php`` examples like::

    define('WP_DEBUG', true);
    define('WP_DEBUG_DISPLAY', true);

…or just the implicit form::

    define('WP_DEBUG', true);
    // (no WP_DEBUG_DISPLAY override -> defaults to true)

What's checked, per file:

  - ``WP_DEBUG`` is defined truthy (``true``/``1``/``"true"``).
  - One of:
      a) ``WP_DEBUG_DISPLAY`` is explicitly defined truthy in the
         same file, OR
      b) ``WP_DEBUG_DISPLAY`` is not defined at all in the file
         AND ``WP_DEBUG_LOG`` is not defined truthy in the file
         (i.e. WordPress falls back to display=on with no log
         redirection).

Accepted (not flagged):

  - ``WP_DEBUG`` is defined falsy (``false``/``0``).
  - ``WP_DEBUG`` is truthy AND ``WP_DEBUG_DISPLAY`` is explicitly
    defined falsy.
  - ``WP_DEBUG`` is truthy AND ``WP_DEBUG_LOG`` is truthy AND
    ``WP_DEBUG_DISPLAY`` is unset (admin opted into log-only).
  - Files containing the comment ``// wp-debug-display-allowed``
    (intentional local-dev override).
  - Files that don't define ``WP_DEBUG`` at all.

Usage::

    python3 detector.py <path> [<path> ...]

Exit code: number of files with at least one finding (capped at
255). Stdout: ``<file>:<line>:<reason>``.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

SUPPRESS = re.compile(r"//\s*wp-debug-display-allowed", re.IGNORECASE)

TRUTHY = {"true", "1"}
FALSY = {"false", "0"}

# Match define('NAME', value);  or  define( "NAME" , value ) ;
DEFINE_RE = re.compile(
    r"""^\s*
        define\s*\(\s*
        (?P<q1>['"])(?P<name>[A-Z_][A-Z0-9_]*)(?P=q1)
        \s*,\s*
        (?P<val>(?:'[^']*'|"[^"]*"|[^,)\s]+))
        \s*(?:,\s*[^)]*)?\)\s*;?
    """,
    re.VERBOSE,
)


def _line_is_active_php(raw: str) -> bool:
    s = raw.lstrip()
    if not s:
        return False
    if s.startswith("//") or s.startswith("#"):
        return False
    if s.startswith("/*") or s.startswith("*"):
        return False
    return True


def _normalize_value(raw_val: str) -> str:
    v = raw_val.strip()
    if (v.startswith("'") and v.endswith("'")) or (
        v.startswith('"') and v.endswith('"')
    ):
        v = v[1:-1]
    return v.lower()


def _strip_block_comments(source: str) -> str:
    return re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)


def scan(source: str) -> List[Tuple[int, str]]:
    findings: List[Tuple[int, str]] = []
    if SUPPRESS.search(source):
        return findings

    cleaned = _strip_block_comments(source)

    defines: Dict[str, Tuple[int, str]] = {}
    for idx, raw in enumerate(cleaned.splitlines(), start=1):
        if not _line_is_active_php(raw):
            continue
        m = DEFINE_RE.match(raw)
        if not m:
            continue
        name = m.group("name").upper()
        if name not in {"WP_DEBUG", "WP_DEBUG_DISPLAY", "WP_DEBUG_LOG"}:
            continue
        val = _normalize_value(m.group("val"))
        defines[name] = (idx, val)

    debug = defines.get("WP_DEBUG")
    if not debug or debug[1] not in TRUTHY:
        return findings

    display = defines.get("WP_DEBUG_DISPLAY")
    log = defines.get("WP_DEBUG_LOG")

    if display and display[1] in TRUTHY:
        findings.append(
            (
                display[0],
                "WordPress WP_DEBUG_DISPLAY=true with WP_DEBUG=true "
                "(CWE-209: errors rendered into HTML response)",
            )
        )
        return findings

    if display and display[1] in FALSY:
        return findings

    # display unset -> defaults to on. Allow only if log is truthy.
    if log and log[1] in TRUTHY:
        return findings

    findings.append(
        (
            debug[0],
            "WordPress WP_DEBUG=true without WP_DEBUG_DISPLAY=false "
            "or WP_DEBUG_LOG=true (display defaults on, CWE-209)",
        )
    )
    return findings


def _is_wp_config(path: Path) -> bool:
    name = path.name.lower()
    if name == "wp-config.php":
        return True
    if name.endswith(".php") and "wp-config" in name:
        return True
    if name.endswith(".php"):
        return True
    return False


def scan_paths(paths: Iterable[Path]) -> int:
    bad_files = 0
    targets: List[Path] = []
    for path in paths:
        if path.is_dir():
            for f in sorted(path.rglob("*")):
                if f.is_file() and _is_wp_config(f):
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
