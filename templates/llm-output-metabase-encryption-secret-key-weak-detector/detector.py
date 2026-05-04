#!/usr/bin/env python3
"""Detect Metabase deployment configurations from LLM output where
``MB_ENCRYPTION_SECRET_KEY`` is missing, empty, or set to a known
weak / placeholder value.

Metabase uses ``MB_ENCRYPTION_SECRET_KEY`` to encrypt the database
connection strings, OAuth client secrets, SAML keys, LDAP bind
credentials, and per-user API tokens stored in its application
database. Upstream guidance (https://www.metabase.com/docs/latest/
operations-guide/encrypting-database-details-at-rest) is explicit:
the key must be generated once with a cryptographic RNG and stored
out-of-band. Yet LLMs that copy the "minimal" docker-compose
example often (a) omit the variable entirely, (b) leave it empty,
or (c) fill it with a literal placeholder such as
``replace-me-with-a-strong-key``. In each case, secrets in the
application database are written in cleartext (case a) or under a
predictable key (cases b/c), and an attacker who exfiltrates the
DB dump trivially recovers every connected source's credentials.

This detector flags four orthogonal regressions:

  1. ``MB_ENCRYPTION_SECRET_KEY`` is referenced (in a Metabase
     config) as an empty string.
  2. ``MB_ENCRYPTION_SECRET_KEY`` is set to a known weak /
     placeholder literal (``changeme``, ``replace-me``,
     ``replace-me-with-a-strong-key``, ``metabase``, ``secret``,
     ``password``, ``0000000000000000``, ``1234567890abcdef``,
     etc., any case).
  3. ``MB_ENCRYPTION_SECRET_KEY`` is set but shorter than the
     16-byte minimum recommended by upstream (Metabase will accept
     it but the key entropy is insufficient).
  4. The file is clearly a Metabase deployment config (mentions
     ``metabase/metabase`` image, ``MB_DB_*`` keys, or the
     ``metabase.jar`` entrypoint) yet ``MB_ENCRYPTION_SECRET_KEY``
     is never declared at all.

Suppression: a top-level ``# metabase-encryption-secret-key-ok``
comment in the file disables all rules (use only for an isolated
lab deployment with no real connected sources).

CWE refs: CWE-321 (Use of Hard-coded Cryptographic Key),
CWE-798 (Use of Hard-coded Credentials),
CWE-1188 (Insecure Default Initialization of Resource).

Public API:
    scan(text: str) -> list[tuple[int, str]]
        Returns a list of (line_number_1based, reason) tuples.
        Empty list = clean.

CLI:
    python3 detector.py <file> [<file> ...]
    Exit code = number of files with at least one finding.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import List, Optional, Tuple

SUPPRESS = re.compile(r"#\s*metabase-encryption-secret-key-ok", re.IGNORECASE)

WEAK_LITERALS = {
    "changeme",
    "change-me",
    "change_me",
    "replace-me",
    "replace_me",
    "replaceme",
    "replace-me-with-a-strong-key",
    "replace-with-a-strong-key",
    "your-secret-key",
    "your-encryption-key",
    "metabase",
    "secret",
    "password",
    "admin",
    "0000000000000000",
    "1111111111111111",
    "1234567890abcdef",
    "0123456789abcdef",
    "aaaaaaaaaaaaaaaa",
    "examplekey",
    "example-key",
    "demo",
}

MIN_KEY_BYTES = 16

# Metabase deployment markers — any one of these is enough to
# decide the file is in scope for rule 4.
METABASE_MARKERS = [
    re.compile(r"\bmetabase/metabase\b", re.IGNORECASE),
    re.compile(r"\bmetabase\.jar\b", re.IGNORECASE),
    re.compile(r"(?ix)(?:^|[\s,;])(?:export\s+)?MB_DB_[A-Z0-9_]+[ \t]*[:=]"),
    re.compile(r"(?ix)(?:^|[\s,;])(?:export\s+)?MB_JETTY_[A-Z0-9_]+[ \t]*[:=]"),
    re.compile(r"(?ix)(?:^|[\s,;])(?:export\s+)?MB_SITE_[A-Z0-9_]+[ \t]*[:=]"),
]


def _env_re(name: str) -> re.Pattern:
    return re.compile(
        r"""(?ix)
        (?:^|[\s,;])
        (?:export\s+)?
        """
        + name
        + r"""
        [ \t]*[:=][ \t]*
        (?P<val>"[^"]*"|'[^']*'|[^\s#,;]*)
        """,
    )


MB_KEY = _env_re("MB_ENCRYPTION_SECRET_KEY")


def _strip(v: Optional[str]) -> str:
    if v is None:
        return ""
    return v.strip().strip("'\"")


def _line_for(lines: List[str], pat: re.Pattern) -> int:
    for i, ln in enumerate(lines, start=1):
        if pat.search(ln):
            return i
    return 1


def _is_metabase_config(text: str) -> bool:
    if MB_KEY.search(text):
        return True
    for m in METABASE_MARKERS:
        if m.search(text):
            return True
    return False


def scan(text: str) -> List[Tuple[int, str]]:
    """Scan a config blob and return findings."""
    if SUPPRESS.search(text):
        return []
    if not _is_metabase_config(text):
        return []
    lines = text.splitlines()
    findings: List[Tuple[int, str]] = []

    key_match = MB_KEY.search(text)

    if key_match is None:
        # Rule 4: looks like Metabase config but key never declared.
        # Anchor to the first marker line.
        anchor_line = 1
        for m in METABASE_MARKERS:
            ln = _line_for(lines, m)
            if ln:
                anchor_line = ln
                break
        findings.append(
            (
                anchor_line,
                "MB_ENCRYPTION_SECRET_KEY is not declared on a Metabase deployment "
                "(database credentials, OAuth client secrets, and API tokens stored "
                "in the application DB will be written in cleartext)",
            )
        )
        return findings

    key_value = _strip(key_match.group("val"))
    key_line = _line_for(lines, MB_KEY)

    if key_value == "":
        findings.append(
            (
                key_line,
                "MB_ENCRYPTION_SECRET_KEY is set to an empty string (Metabase will "
                "treat application-DB secrets as effectively unencrypted)",
            )
        )
        return findings

    if key_value.lower() in WEAK_LITERALS:
        findings.append(
            (
                key_line,
                f"MB_ENCRYPTION_SECRET_KEY is a well-known placeholder ({key_value!r}); "
                "regenerate with a cryptographic RNG before storing real credentials",
            )
        )
        return findings

    if len(key_value.encode("utf-8")) < MIN_KEY_BYTES:
        findings.append(
            (
                key_line,
                f"MB_ENCRYPTION_SECRET_KEY is shorter than {MIN_KEY_BYTES} bytes "
                f"(got {len(key_value)} chars); insufficient entropy for the "
                "AES-derived key",
            )
        )
        return findings

    return findings


def _scan_path(p: Path) -> int:
    try:
        text = p.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        print(f"{p}:0:read-error: {exc}")
        return 0
    hits = scan(text)
    for line, reason in hits:
        print(f"{p}:{line}:{reason}")
    return 1 if hits else 0


def main(argv: List[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 0
    n = 0
    for a in argv[1:]:
        n += _scan_path(Path(a))
    return min(255, n)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
