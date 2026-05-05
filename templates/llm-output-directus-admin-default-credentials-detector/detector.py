#!/usr/bin/env python3
"""Detect Directus configurations whose bootstrap admin account uses
a documented upstream default email or password.

Surfaces scanned:

* ``docker-compose.yml`` / ``compose.yaml`` env blocks (mapping or
  list form) for ``ADMIN_EMAIL`` / ``ADMIN_PASSWORD``.
* ``.envfile`` / ``.env.sample`` style key=value files.
* Helm values / kubernetes manifest snippets using ``adminEmail:`` /
  ``adminPassword:`` keys.
* Shell snippets exporting the same vars before a ``directus bootstrap``
  invocation.

Suppression: a magic comment ``# directus-admin-default-credentials-allowed``
on the same line or the line directly above silences the finding.

Stdlib-only. Exit code is the number of files with at least one
finding (capped at 255). Stdout lines: ``<file>:<line>:<reason>``.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import List, Tuple

SUPPRESS = re.compile(r"#\s*directus-admin-default-credentials-allowed")

# Known upstream defaults from Directus quickstart docs and the
# official directus/directus container image.
WEAK_EMAILS = {
    "admin@example.com",
    "admin@admin.com",
    "admin@directus.io",
}
WEAK_PASSWORDS = {
    "d1r3ctu5",
    "directus",
    "admin",
    "password",
    "changeme",
    "",
}

# docker-compose / .env / shell export style:
#   ADMIN_EMAIL=admin@example.com
#   - ADMIN_EMAIL=admin@example.com
#   export ADMIN_EMAIL="admin@example.com"
ENV_KV = re.compile(
    r"""(?ix)
    ^\s*
    (?:export\s+|-\s+)?
    (ADMIN_EMAIL|ADMIN_PASSWORD)
    \s*[:=]\s*
    (?:"([^"]*)"|'([^']*)'|([^\s#]*))
    \s*(?:\#.*)?$
    """
)

# Helm values / k8s manifest style:
#   adminEmail: admin@example.com
#   admin_password: "d1r3ctu5"
HELM_KV = re.compile(
    r"""(?ix)
    ^\s*
    (admin[_-]?email|admin[_-]?password)
    \s*:\s*
    (?:"([^"]*)"|'([^']*)'|(\S+))
    \s*(?:\#.*)?$
    """
)


def _classify(key: str, value: str) -> Tuple[bool, str]:
    """Return (is_finding, reason). key is normalized lowercase."""
    v = value.strip()
    if "email" in key:
        if v.lower() in WEAK_EMAILS:
            return (
                True,
                f"Directus admin email {v!r} is a documented upstream "
                "default literal",
            )
    elif "password" in key:
        if v.lower() in WEAK_PASSWORDS:
            return (
                True,
                f"Directus admin password {v!r} is a known weak/default "
                "literal (rotate before first boot)",
            )
    return (False, "")


def _scan(source: str) -> List[Tuple[int, str]]:
    findings: List[Tuple[int, str]] = []
    for i, raw in enumerate(source.splitlines(), start=1):
        m = ENV_KV.match(raw)
        if m:
            key = m.group(1).lower()
            value = m.group(2) if m.group(2) is not None else (
                m.group(3) if m.group(3) is not None else (m.group(4) or "")
            )
            hit, reason = _classify(key, value)
            if hit:
                findings.append((i, reason))
            continue
        m = HELM_KV.match(raw)
        if m:
            key = m.group(1).lower().replace("-", "_")
            value = m.group(2) if m.group(2) is not None else (
                m.group(3) if m.group(3) is not None else (m.group(4) or "")
            )
            hit, reason = _classify(key, value)
            if hit:
                findings.append((i, reason))
    return findings


def _filter_suppressed(
    lines: List[str], findings: List[Tuple[int, str]]
) -> List[Tuple[int, str]]:
    out: List[Tuple[int, str]] = []
    for ln, msg in findings:
        same = lines[ln - 1] if 0 < ln <= len(lines) else ""
        prev = lines[ln - 2] if ln - 2 >= 0 else ""
        if SUPPRESS.search(same) or SUPPRESS.search(prev):
            continue
        out.append((ln, msg))
    return out


def scan_file(path: Path) -> List[Tuple[int, str]]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    findings = _scan(text)
    return _filter_suppressed(text.splitlines(), findings)


def main(argv: List[str]) -> int:
    if len(argv) < 2:
        print("usage: detector.py <file> [<file> ...]", file=sys.stderr)
        return 2
    files_with_findings = 0
    for arg in argv[1:]:
        p = Path(arg)
        if not p.is_file():
            continue
        findings = scan_file(p)
        if not findings:
            continue
        files_with_findings += 1
        for ln, msg in findings:
            print(f"{p}:{ln}:{msg}")
    return min(files_with_findings, 255)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
