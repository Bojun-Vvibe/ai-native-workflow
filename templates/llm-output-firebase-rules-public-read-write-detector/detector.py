#!/usr/bin/env python3
"""Detect Firebase / Firestore / Cloud Storage / Realtime Database
security rules that grant unconditional public read or write access.

LLMs asked to "give me Firestore rules so my app works" routinely
emit::

    rules_version = '2';
    service cloud.firestore {
      match /databases/{database}/documents {
        match /{document=**} {
          allow read, write: if true;
        }
      }
    }

…or for Realtime Database::

    {
      "rules": {
        ".read": true,
        ".write": true
      }
    }

Both shapes mean *any unauthenticated client on the public internet
can read every document and overwrite or delete every document*. The
Firebase console emits a daily warning email about this exact
pattern, but LLMs still suggest it as the "fix" when an auth-gated
ruleset blocks an app during development.

What's flagged
--------------
Per file, line-level findings for any of:

* Firestore / Storage rules: ``allow\s+(read|write|create|update|delete|list|get)
  (?:\s*,\s*\w+)*\s*:\s*if\s+true\b`` — the canonical "allow ... :
  if true" shape, including comma-separated verb lists.
* Firestore / Storage rules: ``allow\s+(read|write|...)\s*;`` with no
  ``if`` clause — the unconditional shorthand.
* Realtime Database JSON: ``"\.read"\s*:\s*true`` or
  ``"\.write"\s*:\s*true``.
* Realtime Database JSON: ``"\.read"\s*:\s*"true"`` /
  ``"\.write"\s*:\s*"true"`` (string-typed expression that is
  always-true).

Whole-file finding (line 0):

* A rules file (Firestore / Storage / RTDB) containing a wildcard
  ``match /{document=**}`` or root ``match /`` block whose body has
  a public ``allow`` (per the line rules above) and no
  ``request.auth != null`` / ``auth != null`` / ``auth.uid`` guard
  anywhere in the file.

What's NOT flagged
------------------
* ``allow read, write: if request.auth != null;`` — auth-gated.
* ``allow read: if request.auth.uid == resource.data.ownerId;`` —
  per-document owner check.
* ``".read": "auth != null"`` — RTDB auth check.
* Lines with a trailing ``// fb-rules-public-ok`` or
  ``# fb-rules-public-ok`` comment.
* Files containing ``fb-rules-public-ok-file`` in any comment.

Refs
----
* CWE-284: Improper Access Control
* CWE-732: Incorrect Permission Assignment for Critical Resource
* OWASP Mobile Top 10 (2024) M8: Security Misconfiguration
* Firebase docs — "Get started with Cloud Firestore Security Rules"

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

SUPPRESS_LINE = re.compile(r"(?://|#)\s*fb-rules-public-ok\b")
SUPPRESS_FILE = re.compile(r"fb-rules-public-ok-file\b")

# allow read, write: if true;  | allow read: if true; | allow create, update : if true ;
ALLOW_IF_TRUE = re.compile(
    r"\ballow\s+[a-z]+(?:\s*,\s*[a-z]+)*\s*:\s*if\s+true\b",
    re.IGNORECASE,
)
# allow read;  (no `if` at all — unconditional shorthand)
ALLOW_NO_IF = re.compile(
    r"\ballow\s+[a-z]+(?:\s*,\s*[a-z]+)*\s*;",
    re.IGNORECASE,
)
# RTDB JSON
RTDB_TRUE = re.compile(r'"\s*\.(?:read|write)\s*"\s*:\s*(?:true|"true")\b')

AUTH_GUARD = re.compile(
    r"(?:request\.auth\s*!=\s*null|request\.auth\.uid|auth\s*!=\s*null|auth\.uid)",
)
WILDCARD_MATCH = re.compile(r"match\s+/\{[^}]*=\*\*\}")
ROOT_MATCH = re.compile(r"match\s+/(?:\s|\{)")


def _strip_line_comment(line: str) -> str:
    # rules language uses // and /* */; JSON has no real comments but
    # some templates use // anyway.
    s = line.split("//", 1)[0]
    s = s.split("#", 1)[0]
    return s


def scan(source: str, path: Path) -> List[Tuple[int, str]]:
    findings: List[Tuple[int, str]] = []
    if SUPPRESS_FILE.search(source):
        return findings

    has_wildcard = bool(WILDCARD_MATCH.search(source) or ROOT_MATCH.search(source))
    has_auth_guard = bool(AUTH_GUARD.search(source))
    any_public_allow = False

    for i, raw in enumerate(source.splitlines(), start=1):
        if SUPPRESS_LINE.search(raw):
            continue
        body = _strip_line_comment(raw)

        if ALLOW_IF_TRUE.search(body):
            findings.append((i, "Firebase rule allows unconditional access (`: if true`)"))
            any_public_allow = True
            continue

        # ALLOW_NO_IF: only flag in .rules / firestore.rules / storage.rules
        # contexts to avoid catching unrelated DSLs.
        name = path.name.lower()
        if (
            name.endswith(".rules")
            or "firestore" in name
            or "storage.rules" in name
            or name == "rules"
        ):
            if ALLOW_NO_IF.search(body) and not ALLOW_IF_TRUE.search(body):
                # Don't double-flag if it had `if true`.
                # Also don't flag if line has `if ` somewhere (multi-line).
                if not re.search(r"\bif\b", body):
                    findings.append((
                        i,
                        "Firebase rule uses unconditional `allow ...;` shorthand (no `if` guard)",
                    ))
                    any_public_allow = True
                    continue

        if RTDB_TRUE.search(body):
            findings.append((i, "Realtime Database rule sets `.read`/`.write` to literal true"))
            any_public_allow = True
            continue

    if has_wildcard and any_public_allow and not has_auth_guard:
        findings.append((
            0,
            "wildcard/root `match` block grants public access without any `request.auth` guard",
        ))

    return findings


def _iter_files(path: Path) -> Iterable[Path]:
    if path.is_file():
        yield path
        return
    seen = set()
    patterns = (
        "*.rules",
        "firestore.rules",
        "storage.rules",
        "database.rules.json",
        "*.rules.json",
        "rules.json",
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
