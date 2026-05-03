#!/usr/bin/env python3
"""Detect Gerrit ``gerrit.config`` files whose ``[auth]`` section
sets ``type = DEVELOPMENT_BECOME_ANY_ACCOUNT``.

Gerrit's ``DEVELOPMENT_BECOME_ANY_ACCOUNT`` auth type is documented
strictly as a local-development convenience: it lets any anonymous
visitor "become" any registered account — including the admin
account — by clicking through the "Become" page, with no
credential check. Shipping that value in a network-reachable
``etc/gerrit.config`` is a complete authentication bypass
(CWE-287, CWE-1188).

The Gerrit config file format is git-config style::

    [auth]
        type = DEVELOPMENT_BECOME_ANY_ACCOUNT
    [gerrit]
        canonicalWebUrl = http://gerrit.example.com/

LLM-generated bootstrap configs and Dockerfile ``CMD`` lines often
emit this value verbatim because it is the simplest auth setting
in every "first run" tutorial.

What's checked (per file whose name is ``gerrit.config`` or whose
contents look like Gerrit config):
  - The file contains an active ``[auth]`` section header.
  - Inside that section (until the next ``[section]`` header), an
    active ``type`` key is set to ``DEVELOPMENT_BECOME_ANY_ACCOUNT``
    (case-insensitive on the key, exact on the value as Gerrit
    parses the string case-sensitively).
  - Comment lines (starting with ``#`` or ``;``) are ignored.
  - Inline comments after ``;`` or ``#`` are stripped from values.

Also catches ``-c auth.type=DEVELOPMENT_BECOME_ANY_ACCOUNT`` style
overrides in shell scripts, Dockerfiles, and systemd unit files
where Gerrit is launched with ``java -jar gerrit.war ... -c
auth.type=...`` or ``--config auth.type=...``. To avoid false
positives this CLI form is only flagged on lines that also mention
``gerrit`` or ``GerritCodeReview``.

Accepted (not flagged):
  - Any other ``auth.type`` value (``OAUTH``, ``LDAP``,
    ``HTTP``, ``OPENID``, ``CUSTOM_EXTENSION``, etc.).
  - Files containing the marker comment
    ``# gerrit-development-auth-allowed`` (skipped wholesale,
    intended for local-only smoke fixtures).

CWE refs:
  - CWE-287: Improper Authentication
  - CWE-1188: Insecure Default Initialization of Resource
  - CWE-306: Missing Authentication for Critical Function

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

SUPPRESS = re.compile(r"[#;]\s*gerrit-development-auth-allowed", re.IGNORECASE)

SECTION_RE = re.compile(r"^\s*\[\s*([A-Za-z0-9_.\-]+)(?:\s+\"[^\"]*\")?\s*\]\s*$")
KV_RE = re.compile(r"^\s*([A-Za-z0-9_.\-]+)\s*=\s*(.+?)\s*$")

DEV_VALUE = "DEVELOPMENT_BECOME_ANY_ACCOUNT"

# CLI override form, e.g. `-c auth.type=DEVELOPMENT_BECOME_ANY_ACCOUNT`
CLI_RE = re.compile(
    r"(?:-c|--config)\s+auth\.type\s*=\s*DEVELOPMENT_BECOME_ANY_ACCOUNT\b"
)


def _strip_inline_comment(value: str) -> str:
    """Strip ``;`` or ``#`` inline comments from a git-config
    value, leaving quoted strings alone."""
    out = []
    in_quote = False
    quote_char = ""
    for ch in value:
        if in_quote:
            out.append(ch)
            if ch == quote_char:
                in_quote = False
            continue
        if ch in {'"', "'"}:
            in_quote = True
            quote_char = ch
            out.append(ch)
            continue
        if ch in {"#", ";"}:
            break
        out.append(ch)
    result = "".join(out).strip()
    if len(result) >= 2 and result[0] == result[-1] and result[0] in {'"', "'"}:
        result = result[1:-1]
    return result


def _looks_like_gerrit_config(source: str) -> bool:
    return bool(
        re.search(r"^\s*\[auth\]", source, re.MULTILINE)
        or re.search(r"^\s*\[gerrit\]", source, re.MULTILINE)
        or re.search(r"^\s*\[receive\]", source, re.MULTILINE)
        or "GerritCodeReview" in source
    )


def scan(source: str, filename: str = "") -> List[Tuple[int, str]]:
    findings: List[Tuple[int, str]] = []
    if SUPPRESS.search(source):
        return findings

    is_config = filename.endswith("gerrit.config") or _looks_like_gerrit_config(source)

    if is_config:
        current_section = ""
        for idx, raw in enumerate(source.splitlines(), start=1):
            stripped = raw.strip()
            if not stripped:
                continue
            if stripped.startswith("#") or stripped.startswith(";"):
                continue
            section_m = SECTION_RE.match(raw)
            if section_m:
                current_section = section_m.group(1).lower()
                continue
            if current_section != "auth":
                continue
            kv_m = KV_RE.match(raw)
            if not kv_m:
                continue
            key = kv_m.group(1).lower()
            if key != "type":
                continue
            value = _strip_inline_comment(kv_m.group(2))
            if value == DEV_VALUE:
                findings.append(
                    (
                        idx,
                        "Gerrit [auth] type set to "
                        "DEVELOPMENT_BECOME_ANY_ACCOUNT: any visitor "
                        "can impersonate any account",
                    )
                )

    # CLI / Dockerfile / unit file form: only flag lines that also
    # name Gerrit (on the line, the file name, or anywhere in the
    # source) to keep false-positive surface tight.
    file_mentions_gerrit = (
        "gerrit" in source.lower() or "GerritCodeReview" in source
    )
    for idx, raw in enumerate(source.splitlines(), start=1):
        stripped = raw.lstrip()
        if not stripped or stripped.startswith("#"):
            continue
        if not CLI_RE.search(raw):
            continue
        line_mentions = ("gerrit" in raw.lower()) or ("GerritCodeReview" in raw)
        if line_mentions or file_mentions_gerrit:
            findings.append(
                (
                    idx,
                    "Gerrit launched with -c auth.type="
                    "DEVELOPMENT_BECOME_ANY_ACCOUNT override",
                )
            )

    return findings


def _is_target(path: Path) -> bool:
    name = path.name.lower()
    if name == "gerrit.config":
        return True
    if name.endswith((".sh", ".bash", ".service", ".env")):
        return True
    if name in {"dockerfile"} or name.startswith("dockerfile."):
        return True
    return False


def scan_paths(paths: Iterable[Path]) -> int:
    bad_files = 0
    targets: List[Path] = []
    for path in paths:
        if path.is_dir():
            for f in sorted(path.rglob("*")):
                if f.is_file() and _is_target(f):
                    targets.append(f)
        else:
            targets.append(path)
    for f in targets:
        try:
            source = f.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            print(f"{f}:0:read-error: {exc}")
            continue
        hits = scan(source, filename=f.name)
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
