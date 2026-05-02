#!/usr/bin/env python3
"""Detect Dovecot IMAP/POP3 server configuration files that allow
plaintext authentication over unencrypted connections by setting
``disable_plaintext_auth = no`` (or by leaving the SSL stack
disabled while keeping the plaintext PLAIN/LOGIN auth mechanisms).

Background
----------
Dovecot's default ``disable_plaintext_auth = yes`` refuses PLAIN
and LOGIN auth over a non-TLS connection, which is the only thing
preventing every shared-WiFi attacker on the network from
trivially harvesting mailbox credentials. The single line::

    disable_plaintext_auth = no

undoes that and is one of the most common "but it works on my
laptop" footguns LLMs emit when a user complains about a Thunder-
bird / mutt / fetchmail client failing to log in.

A second, sneakier failure mode is::

    ssl = no
    auth_mechanisms = plain login

…which leaves ``disable_plaintext_auth`` at the default ``yes`` —
but with ``ssl = no`` there is *no* TLS to gate plaintext on, so
plaintext is effectively the only path and Dovecot will happily
accept it on port 143 / 110.

What's flagged
--------------
Per file, line-level findings:

* ``disable_plaintext_auth = no``
* ``ssl = no`` on a file that also contains ``auth_mechanisms``
  including ``plain`` or ``login`` (whole-file finding, line 0).
* ``auth_mechanisms`` containing only ``plain``/``login`` AND no
  TLS-wrapped listener anywhere in the file (whole-file finding,
  line 0).

Whole-file finding (line 0):

* The file looks like a top-level Dovecot server config (contains
  ``protocols =``, ``listen =``, ``mail_location =``, or a
  ``service imap-login`` / ``service pop3-login`` block) AND it
  does not set ``disable_plaintext_auth = yes`` AND it does not
  set ``ssl = required``. The Dovecot default is ``yes``/``no``
  respectively, so a config that *opts in* to laxer auth without
  saying so is exactly the failure mode we care about — but only
  if it also weakens the SSL stack, otherwise the default is fine.

What's NOT flagged
------------------
* ``disable_plaintext_auth = yes``
* ``ssl = required``
* Pure include fragments that contain only ``passdb`` / ``userdb``
  / ``namespace`` blocks and no top-level server-identity
  directives.
* Lines with a trailing ``# dovecot-plain-ok`` comment.
* Files containing ``dovecot-plain-ok-file`` in any comment.

Refs
----
* CWE-319: Cleartext Transmission of Sensitive Information
* CWE-523: Unprotected Transport of Credentials
* OWASP ASVS v4 §9.1.1 — TLS for all auth surfaces
* Dovecot wiki — ``disable_plaintext_auth`` and ``ssl``

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

SUPPRESS_LINE = re.compile(r"#\s*dovecot-plain-ok\b")
SUPPRESS_FILE = re.compile(r"dovecot-plain-ok-file\b")

PLAIN_AUTH_NO = re.compile(
    r"^\s*disable_plaintext_auth\s*=\s*no\b", re.IGNORECASE
)
PLAIN_AUTH_YES = re.compile(
    r"^\s*disable_plaintext_auth\s*=\s*yes\b", re.IGNORECASE
)
SSL_NO = re.compile(r"^\s*ssl\s*=\s*no\b", re.IGNORECASE)
SSL_REQUIRED = re.compile(r"^\s*ssl\s*=\s*required\b", re.IGNORECASE)
SSL_YES = re.compile(r"^\s*ssl\s*=\s*yes\b", re.IGNORECASE)
AUTH_MECH = re.compile(
    r"^\s*auth_mechanisms\s*=\s*(.+)$", re.IGNORECASE
)

TOP_LEVEL_HINT = re.compile(
    r"^\s*(protocols\s*=|listen\s*=|mail_location\s*=|service\s+imap-login\b|service\s+pop3-login\b)",
    re.IGNORECASE | re.MULTILINE,
)


def _strip_comment(line: str) -> str:
    return line.split("#", 1)[0]


def scan(source: str) -> List[Tuple[int, str]]:
    findings: List[Tuple[int, str]] = []
    if SUPPRESS_FILE.search(source):
        return findings

    has_plain_yes = False
    has_ssl_required = False
    has_ssl_no_line = 0
    has_top_level = bool(TOP_LEVEL_HINT.search(source))
    plain_mechs = False  # auth_mechanisms includes plain/login

    for i, raw in enumerate(source.splitlines(), start=1):
        if SUPPRESS_LINE.search(raw):
            body = _strip_comment(raw)
            if PLAIN_AUTH_YES.match(body):
                has_plain_yes = True
            if SSL_REQUIRED.match(body):
                has_ssl_required = True
            continue
        body = _strip_comment(raw)

        if PLAIN_AUTH_NO.match(body):
            findings.append(
                (
                    i,
                    "`disable_plaintext_auth = no` lets Dovecot accept PLAIN/LOGIN auth over cleartext",
                )
            )
            continue
        if PLAIN_AUTH_YES.match(body):
            has_plain_yes = True
            continue

        if SSL_NO.match(body):
            has_ssl_no_line = i
            continue
        if SSL_REQUIRED.match(body):
            has_ssl_required = True
            continue

        m = AUTH_MECH.match(body)
        if m:
            mechs = m.group(1).lower()
            tokens = re.split(r"[\s,]+", mechs.strip())
            if any(tok in ("plain", "login") for tok in tokens):
                plain_mechs = True

    if has_ssl_no_line and plain_mechs:
        findings.append(
            (
                has_ssl_no_line,
                "`ssl = no` together with PLAIN/LOGIN auth_mechanisms forces credentials over cleartext",
            )
        )

    if (
        has_top_level
        and not has_plain_yes
        and not has_ssl_required
        and (has_ssl_no_line or plain_mechs)
    ):
        if not any(line == 0 for line, _ in findings):
            missing = []
            if not has_plain_yes:
                missing.append("`disable_plaintext_auth = yes`")
            if not has_ssl_required:
                missing.append("`ssl = required`")
            findings.append(
                (
                    0,
                    "top-level Dovecot config weakens SSL/auth and is missing "
                    + " and ".join(missing),
                )
            )

    return findings


def _iter_files(path: Path) -> Iterable[Path]:
    if path.is_file():
        yield path
        return
    seen = set()
    patterns = (
        "dovecot.conf",
        "dovecot/*.conf",
        "conf.d/*.conf",
        "*.dovecot.conf",
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
