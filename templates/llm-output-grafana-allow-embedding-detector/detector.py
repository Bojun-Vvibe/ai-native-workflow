#!/usr/bin/env python3
"""Detect Grafana ``grafana.ini`` (and ``custom.ini``) files where
``allow_embedding = true`` is set in the ``[security]`` section,
disabling Grafana's default frame-busting / clickjacking defenses.

Grafana ships with ``allow_embedding = false`` by default. When set to
``true``, Grafana drops the ``X-Frame-Options: DENY`` header (and the
``frame-ancestors`` CSP) from its responses, so any external site can
embed Grafana panels in an ``<iframe>``. Combined with cookie-based
session auth, this enables clickjacking attacks against Grafana
admins (e.g. an attacker site frames Grafana, overlays a transparent
button, and tricks the admin into clicking "Delete data source" or
"Add admin user").

What's checked (per file):
  - ``allow_embedding = true`` (case-insensitive, with or without
    spaces around ``=``) inside the ``[security]`` section.
  - Same key set at top-level (no section header) is treated the same
    way because Grafana's ini parser also accepts it as a security
    key when no other section is active.
  - ``cookie_samesite = none`` in the same file is captured to
    escalate the finding to "embeddable + SameSite=None cookie".

CWE refs:
  - CWE-1021: Improper Restriction of Rendered UI Layers or Frames
    (Clickjacking)
  - CWE-693: Protection Mechanism Failure
  - CWE-1275: Sensitive Cookie with Improper SameSite Attribute (when
    paired with ``cookie_samesite = none``)

False-positive surface:
  - Embedding Grafana panels into a trusted internal portal that is
    served on the same origin / behind the same SSO. Suppress per
    file with a comment ``# grafana-embedding-allowed`` anywhere in
    the file.
  - ``allow_embedding = false`` (the default) is treated as safe.

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

SUPPRESS = re.compile(r"[#;]\s*grafana-embedding-allowed")

SECTION_RE = re.compile(r"^\s*\[(?P<name>[^\]]+)\]\s*$")
ALLOW_EMBED_RE = re.compile(
    r"""^\s*allow_embedding\s*=\s*(?P<val>['"]?[^#;\n]+?['"]?)\s*(?:[#;].*)?$""",
    re.IGNORECASE,
)
SAMESITE_NONE_RE = re.compile(
    r"""^\s*cookie_samesite\s*=\s*['"]?none['"]?\s*(?:[#;].*)?$""",
    re.IGNORECASE,
)

TRUE_VALUES = {"true", "1", "yes", "on"}


def _normalize(value: str) -> str:
    return value.strip().strip("'\"").strip().lower()


def scan(source: str) -> List[Tuple[int, str]]:
    findings: List[Tuple[int, str]] = []
    if SUPPRESS.search(source):
        return findings

    section = ""
    embed_line = 0
    samesite_none_line = 0

    for i, raw in enumerate(source.splitlines(), start=1):
        stripped = raw.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith(";"):
            continue

        sec = SECTION_RE.match(raw)
        if sec:
            section = sec.group("name").strip().lower()
            continue

        m = ALLOW_EMBED_RE.match(raw)
        if m and section in ("security", ""):
            val = _normalize(m.group("val"))
            if val in TRUE_VALUES:
                embed_line = i
            continue

        if SAMESITE_NONE_RE.match(raw) and section in ("security", ""):
            samesite_none_line = i
            continue

    if embed_line:
        if samesite_none_line:
            findings.append((
                embed_line,
                f"allow_embedding=true AND cookie_samesite=none on line "
                f"{samesite_none_line} — Grafana embeddable cross-site with "
                f"cookies sent → clickjacking + cross-site session abuse",
            ))
        else:
            findings.append((
                embed_line,
                "allow_embedding=true disables X-Frame-Options/frame-ancestors → "
                "clickjacking risk against Grafana admins",
            ))

    return findings


def scan_paths(paths: Iterable[Path]) -> int:
    bad_files = 0
    targets: List[Path] = []
    for path in paths:
        if path.is_dir():
            for ext in ("grafana.ini", "custom.ini", "*.grafana.ini"):
                targets.extend(sorted(path.rglob(ext)))
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
