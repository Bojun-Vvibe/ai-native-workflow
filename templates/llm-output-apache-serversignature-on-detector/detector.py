#!/usr/bin/env python3
"""Detect Apache httpd configuration files that leak the server
identity by enabling ``ServerSignature`` and/or by leaving
``ServerTokens`` at the default ``Full`` level.

Background
----------
Apache httpd, by default, attaches a verbose ``Server`` response
header on every reply::

    Server: Apache/2.4.58 (Ubuntu) OpenSSL/3.0.13 mod_wsgi/4.9.4

…and, when ``ServerSignature On`` (or ``EMail``) is set, prints the
same string at the bottom of every auto-generated error page
(404, 500, directory listings, mod_status output, etc.). Either of
those is a reconnaissance gift: the version + module list pins down
the exact CVE list and module ABI an attacker should target.

The hardened recipe is two lines, both inside the main server
config (NOT inside a ``<Directory>`` / ``<Location>`` block, where
they are silently ignored)::

    ServerTokens Prod
    ServerSignature Off

LLMs frequently miss one or both of these because the canonical
``httpd.conf`` shipped by every distro and every "set up Apache as
a reverse proxy" tutorial does not include them.

What's flagged
--------------
Per file, line-level findings:

* ``ServerSignature On``           — enables the footer banner.
* ``ServerSignature EMail``        — enables footer banner + mailto.
* ``ServerTokens Full``            — explicit full version banner.
* ``ServerTokens OS``              — version + OS, still verbose.
* ``ServerTokens Major`` / ``Minor`` / ``Min`` — verbose-ish.

Whole-file finding (line 0):

* The file looks like a top-level Apache server config (contains
  ``Listen``, ``<VirtualHost``, ``ServerName``, or
  ``DocumentRoot``) AND it does not set ``ServerSignature Off``
  AND it does not set ``ServerTokens Prod`` (or ``Prod``-equivalent
  ``ProductOnly``). This catches the "default-leaky" config where
  the author simply forgot.

What's NOT flagged
------------------
* ``ServerSignature Off``
* ``ServerTokens Prod`` / ``ProductOnly``
* Pure include fragments that contain only ``<Directory>`` /
  ``<Location>`` / ``Alias`` rules and no top-level server
  directives.
* Lines with a trailing ``# httpd-sig-ok`` comment.
* Files containing ``httpd-sig-ok-file`` in any comment.

Refs
----
* CWE-200: Exposure of Sensitive Information to an Unauthorized Actor
* CWE-209: Generation of Error Message Containing Sensitive
  Information
* OWASP ASVS v4 §14.3.2 — HTTP banner / version disclosure
* Apache httpd docs — ``ServerSignature``, ``ServerTokens``

Usage
-----
    python3 detector.py <file_or_dir> [...]

Exit code: number of files with at least one finding (capped 255).
Stdout:    ``<file>:<line>:<reason>``.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Iterable, List, Tuple

SUPPRESS_LINE = re.compile(r"#\s*httpd-sig-ok\b")
SUPPRESS_FILE = re.compile(r"httpd-sig-ok-file\b")

SIG_ON = re.compile(r"^\s*ServerSignature\s+On\b", re.IGNORECASE)
SIG_EMAIL = re.compile(r"^\s*ServerSignature\s+EMail\b", re.IGNORECASE)
SIG_OFF = re.compile(r"^\s*ServerSignature\s+Off\b", re.IGNORECASE)

TOKENS_FULL = re.compile(r"^\s*ServerTokens\s+Full\b", re.IGNORECASE)
TOKENS_OS = re.compile(r"^\s*ServerTokens\s+OS\b", re.IGNORECASE)
TOKENS_MAJOR = re.compile(r"^\s*ServerTokens\s+Major\b", re.IGNORECASE)
TOKENS_MINOR = re.compile(r"^\s*ServerTokens\s+Minor\b", re.IGNORECASE)
TOKENS_MIN = re.compile(r"^\s*ServerTokens\s+Min\b", re.IGNORECASE)
TOKENS_PROD = re.compile(
    r"^\s*ServerTokens\s+(Prod|ProductOnly)\b", re.IGNORECASE
)

TOP_LEVEL_HINT = re.compile(
    r"^\s*(Listen\s+|<VirtualHost\b|ServerName\s+|DocumentRoot\s+)",
    re.IGNORECASE | re.MULTILINE,
)


def _strip_comment(line: str) -> str:
    return line.split("#", 1)[0]


def scan(source: str) -> List[Tuple[int, str]]:
    findings: List[Tuple[int, str]] = []
    if SUPPRESS_FILE.search(source):
        return findings

    has_sig_off = False
    has_tokens_prod = False
    is_top_level = bool(TOP_LEVEL_HINT.search(source))

    for i, raw in enumerate(source.splitlines(), start=1):
        if SUPPRESS_LINE.search(raw):
            body = _strip_comment(raw)
            if SIG_OFF.match(body):
                has_sig_off = True
            if TOKENS_PROD.match(body):
                has_tokens_prod = True
            continue
        body = _strip_comment(raw)

        if SIG_ON.match(body):
            findings.append(
                (i, "`ServerSignature On` prints version banner on every error page")
            )
            continue
        if SIG_EMAIL.match(body):
            findings.append(
                (
                    i,
                    "`ServerSignature EMail` prints version banner + admin mailto on error pages",
                )
            )
            continue
        if SIG_OFF.match(body):
            has_sig_off = True
            continue

        if TOKENS_FULL.match(body):
            findings.append(
                (i, "`ServerTokens Full` exposes Apache version + OS + modules in Server header")
            )
            continue
        if TOKENS_OS.match(body):
            findings.append(
                (i, "`ServerTokens OS` exposes Apache version + OS in Server header")
            )
            continue
        if TOKENS_MAJOR.match(body):
            findings.append(
                (i, "`ServerTokens Major` still leaks Apache major version in Server header")
            )
            continue
        if TOKENS_MINOR.match(body):
            findings.append(
                (i, "`ServerTokens Minor` still leaks Apache minor version in Server header")
            )
            continue
        if TOKENS_MIN.match(body):
            findings.append(
                (i, "`ServerTokens Min` still leaks Apache patch version in Server header")
            )
            continue
        if TOKENS_PROD.match(body):
            has_tokens_prod = True

    if is_top_level and not (has_sig_off and has_tokens_prod):
        if not findings:
            missing = []
            if not has_sig_off:
                missing.append("`ServerSignature Off`")
            if not has_tokens_prod:
                missing.append("`ServerTokens Prod`")
            findings.append(
                (
                    0,
                    "top-level Apache config missing " + " and ".join(missing)
                    + " — defaults leak Apache version",
                )
            )

    return findings


def _iter_files(path: Path) -> Iterable[Path]:
    if path.is_file():
        yield path
        return
    seen = set()
    patterns = (
        "httpd.conf",
        "apache2.conf",
        "*.conf",
        "conf.d/*.conf",
        "sites-available/*",
        "sites-enabled/*",
    )
    for pattern in patterns:
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
