#!/usr/bin/env python3
"""Detect nginx configuration files that explicitly enable
``server_tokens on;`` or rely on the insecure default by serving
HTTP without ever turning it off.

Background
----------
By default, nginx returns its full version string in the ``Server``
response header and on auto-generated error pages
(e.g. ``Server: nginx/1.25.3``). That version string is the single
most useful piece of reconnaissance for an attacker: it pins down
the exact CVE list applicable to the server. The fix is one line::

    server_tokens off;

…placed in the ``http`` block. LLMs asked to "write me an nginx
config" almost never include it, because the canonical
``nginx.conf`` shipped by every distro and every "hello world"
tutorial does not include it either. Worse, models sometimes emit
``server_tokens on;`` explicitly, copying from "show me everything
nginx can do" example files.

What's flagged
--------------
Per file, line-level findings:

* ``server_tokens on;`` — explicit version banner.
* ``server_tokens build;`` — even louder (also leaks build name).

Whole-file finding (line 0):

* The file contains an ``http {`` block AND no
  ``server_tokens off;`` (or ``server_tokens  build;`` already
  flagged) AND no ``more_clear_headers Server;`` /
  ``more_set_headers 'Server: ...';`` (third-party
  ``ngx_http_headers_more`` module that masks the header). This
  catches the "default-leaky" config where the author simply
  forgot.

What's NOT flagged
------------------
* ``server_tokens off;``
* Files using ``more_clear_headers Server;`` or
  ``more_set_headers 'Server: ...';`` to mask the header.
* Files that are not ``http``-block configs (a plain ``stream {}``
  TCP-load-balancer config, a ``mail {}`` config, an included
  fragment that has no ``http {`` of its own).
* Lines with a trailing ``# ngx-tokens-ok`` comment.
* Files containing ``ngx-tokens-ok-file`` in any comment.

Refs
----
* CWE-200: Exposure of Sensitive Information to an Unauthorized Actor
* CWE-209: Generation of Error Message Containing Sensitive
  Information
* OWASP ASVS v4 §14.3.2 — HTTP banner / version disclosure
* nginx docs — ``server_tokens`` directive

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

SUPPRESS_LINE = re.compile(r"#\s*ngx-tokens-ok\b")
SUPPRESS_FILE = re.compile(r"ngx-tokens-ok-file\b")

TOKENS_ON = re.compile(r"^\s*server_tokens\s+on\s*;", re.IGNORECASE)
TOKENS_BUILD = re.compile(r"^\s*server_tokens\s+build\s*;", re.IGNORECASE)
TOKENS_OFF = re.compile(r"^\s*server_tokens\s+off\s*;", re.IGNORECASE)

HTTP_BLOCK = re.compile(r"^\s*http\s*\{")
MORE_CLEAR_SERVER = re.compile(
    r"more_clear_headers\s+['\"]?Server['\"]?\s*;",
    re.IGNORECASE,
)
MORE_SET_SERVER = re.compile(
    r"more_set_headers\s+['\"]Server\s*:",
    re.IGNORECASE,
)


def _strip_comment(line: str) -> str:
    return line.split("#", 1)[0]


def scan(source: str) -> List[Tuple[int, str]]:
    findings: List[Tuple[int, str]] = []
    if SUPPRESS_FILE.search(source):
        return findings

    has_http_block = False
    has_off = False
    has_mask = bool(MORE_CLEAR_SERVER.search(source) or MORE_SET_SERVER.search(source))

    for i, raw in enumerate(source.splitlines(), start=1):
        if SUPPRESS_LINE.search(raw):
            # Suppressed line still counts toward "has_off" if it is one.
            body = _strip_comment(raw)
            if TOKENS_OFF.match(body):
                has_off = True
            if HTTP_BLOCK.match(body):
                has_http_block = True
            continue
        body = _strip_comment(raw)

        if HTTP_BLOCK.match(body):
            has_http_block = True

        if TOKENS_ON.match(body):
            findings.append((i, "`server_tokens on;` exposes nginx version in Server header"))
            continue
        if TOKENS_BUILD.match(body):
            findings.append((i, "`server_tokens build;` exposes nginx version + build name"))
            continue
        if TOKENS_OFF.match(body):
            has_off = True

    if has_http_block and not has_off and not has_mask:
        # Don't double-up if we already flagged an explicit `on`.
        if not any("server_tokens" in r for _, r in findings):
            findings.append((
                0,
                "http {} block has no `server_tokens off;` — defaults to leaking nginx version",
            ))

    return findings


def _iter_files(path: Path) -> Iterable[Path]:
    if path.is_file():
        yield path
        return
    seen = set()
    patterns = (
        "nginx.conf",
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
