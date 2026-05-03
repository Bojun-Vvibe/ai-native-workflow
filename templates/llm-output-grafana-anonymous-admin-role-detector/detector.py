#!/usr/bin/env python3
"""Detect Grafana INI configurations whose ``[auth.anonymous]``
section has ``enabled = true`` together with ``org_role`` set to
``Admin`` or ``Editor``.

Grafana's anonymous-auth mode lets unauthenticated visitors act as
a real user inside an organization. With ``org_role = Viewer`` (the
shipped default), that's only read access to dashboards. With
``org_role = Editor`` or ``org_role = Admin``, an unauthenticated
visitor on the network can mutate dashboards, install plugins,
add data sources, exfiltrate query results from any backing
database, and — for ``Admin`` — manage org users and API keys
(CWE-862, CWE-732).

LLM-generated ``grafana.ini`` files routinely emit shapes like::

    [auth.anonymous]
    enabled = true
    org_role = Admin

or::

    [auth.anonymous]
    enabled  = true
    org_name = Main Org.
    org_role = Editor

This detector parses each INI section and flags
``[auth.anonymous]`` sections where ``enabled`` is truthy AND
``org_role`` is ``Admin`` or ``Editor`` (case-insensitive).

What's checked (per file):
  - The single ``[auth.anonymous]`` section.
  - ``enabled`` set to ``true``, ``True``, ``1``, ``yes``, ``on``
    (Grafana's accepted truthy forms).
  - ``org_role`` set to ``Admin`` or ``Editor`` (case-insensitive,
    quotes stripped).

Accepted (not flagged):
  - ``enabled = false`` regardless of ``org_role``.
  - ``org_role = Viewer`` (the documented read-only kiosk pattern).
  - Files containing the comment ``# grafana-anon-admin-allowed``
    are skipped wholesale (intentional kiosk fixtures).
  - Sections other than ``[auth.anonymous]``.

CWE refs:
  - CWE-862: Missing Authorization
  - CWE-732: Incorrect Permission Assignment for Critical Resource
  - CWE-284: Improper Access Control

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

SUPPRESS = re.compile(r"#\s*grafana-anon-admin-allowed", re.IGNORECASE)

SECTION_RE = re.compile(r"^\s*\[(?P<name>[^\]]+)\]\s*(?:[;#].*)?$")
KV_RE = re.compile(
    r"^\s*(?P<key>[A-Za-z_][A-Za-z0-9_.-]*)\s*=\s*(?P<value>.*?)\s*(?:[;#].*)?$"
)

TRUE_VALUES = {"true", "1", "yes", "on"}
ELEVATED_ROLES = {"admin", "editor"}


def _strip_quotes(s: str) -> str:
    s = s.strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in {'"', "'"}:
        return s[1:-1]
    return s


def scan(source: str) -> List[Tuple[int, str]]:
    findings: List[Tuple[int, str]] = []
    if SUPPRESS.search(source):
        return findings

    lines = source.splitlines()
    current_section = ""

    # Per-section accumulator for the section we care about. Grafana
    # allows an INI section to appear more than once (rare but legal);
    # we evaluate each occurrence independently.
    enabled_value = ""
    enabled_line = 0
    role_value = ""
    role_line = 0
    section_header_line = 0

    def _flush() -> None:
        if current_section.lower() != "auth.anonymous":
            return
        if _strip_quotes(enabled_value).lower() not in TRUE_VALUES:
            return
        role = _strip_quotes(role_value).lower()
        if role not in ELEVATED_ROLES:
            return
        line = role_line or enabled_line or section_header_line or 1
        findings.append(
            (
                line,
                f"grafana [auth.anonymous] enabled={enabled_value} "
                f"with org_role={_strip_quotes(role_value)} "
                f"grants unauthenticated {_strip_quotes(role_value).lower()} access",
            )
        )

    for idx, raw in enumerate(lines, start=1):
        sec = SECTION_RE.match(raw)
        if sec:
            # Close out any pending section before switching.
            _flush()
            current_section = sec.group("name").strip()
            enabled_value = ""
            enabled_line = 0
            role_value = ""
            role_line = 0
            section_header_line = idx
            continue

        # Skip blank / comment-only lines.
        stripped = raw.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith(";"):
            continue

        if current_section.lower() != "auth.anonymous":
            continue

        kv = KV_RE.match(raw)
        if not kv:
            continue
        key = kv.group("key").strip().lower()
        val = kv.group("value").strip()
        if key == "enabled":
            enabled_value = val
            enabled_line = idx
        elif key == "org_role":
            role_value = val
            role_line = idx

    # Flush trailing section.
    _flush()
    return findings


def _is_grafana_ini(path: Path) -> bool:
    name = path.name.lower()
    if name in {"grafana.ini", "custom.ini", "defaults.ini"}:
        return True
    if name.endswith(".ini") and "grafana" in str(path).lower():
        return True
    return False


def scan_paths(paths: Iterable[Path]) -> int:
    bad_files = 0
    targets: List[Path] = []
    for path in paths:
        if path.is_dir():
            for f in sorted(path.rglob("*")):
                if f.is_file() and _is_grafana_ini(f):
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
