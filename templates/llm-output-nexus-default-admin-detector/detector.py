#!/usr/bin/env python3
"""Detect Sonatype Nexus Repository Manager 3 deployment artifacts
that ship the well-known default admin credential ``admin/admin123``
(or the legacy default password file ``/nexus-data/admin.password``
left exposed in a baked image), and detect provisioning scripts that
seed an admin via the REST API with a trivial password.

Background. Nexus 3 generates a one-time admin password on first
startup, written to ``/nexus-data/admin.password``. The intended
workflow is: read the file, log in once, set a real password, delete
the file. In practice, LLM-suggested Dockerfiles either
``ENV NEXUS_SECURITY_INITIAL_PASSWORD=admin123`` (or ``admin``), bake
``admin.password`` containing ``admin123`` into the image, or call
``PUT /service/rest/v1/security/users/admin/change-password`` with
``admin123`` as the body. All three reproduce the famous Nexus default
that has been catalogued in CISA KEV-adjacent intrusions for years.

What's checked (per file):
  - ``NEXUS_SECURITY_INITIAL_PASSWORD`` / ``NEXUS_SECURITY_RANDOMPASSWORD=false``
    pair where the initial password is in the trivial set, or
    randompassword is disabled with no replacement set.
  - Dockerfile / compose / k8s manifests that ``COPY`` or mount a
    file literally named ``admin.password`` into ``/nexus-data/`` —
    that's the bootstrap secret leaking into a container image layer.
  - Shell / Groovy / Ansible snippets that POST/PUT to
    ``/service/rest/v1/security/users/admin/change-password`` with a
    request body whose body is in the trivial password set.
  - ``-Dnexus.security.randompassword=false`` JVM flag without a
    paired non-trivial ``-Dnexus.security.initialPassword=...``.

Findings are reported per-line.

CWE refs:
  - CWE-798: Use of Hard-coded Credentials
  - CWE-1392: Use of Default Credentials
  - CWE-256: Plaintext Storage of a Password

False-positive surface:
  - ``${VAR}`` / ``$(...)`` / ``{{ ... }}`` / ``<<TOKEN>>`` placeholders
    are treated as unresolved templating and not flagged.
  - Files containing the marker ``# nexus-default-admin-allowed`` are
    suppressed (e.g. ephemeral CI fixtures, throwaway test images).

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

SUPPRESS = re.compile(r"#\s*nexus-default-admin-allowed")

TRIVIAL = {
    "admin",
    "admin123",
    "administrator",
    "nexus",
    "password",
    "passw0rd",
    "changeme",
    "change-me",
    "root",
    "12345",
    "123456",
    "qwerty",
    "letmein",
    "secret",
    "default",
}

# 1. Initial-password env / JVM flag (with trivial value).
INITIAL_PW_RE = re.compile(
    r"""
    (?:^|[\s,;])
    (?P<key>NEXUS_SECURITY_INITIAL_PASSWORD
        |nexus\.security\.initialPassword)
    \s*[:=]\s*
    (?P<val>"[^"]*"|'[^']*'|[^\s,;]+)
    """,
    re.VERBOSE,
)

# 2. Disabling random-password generation (with no replacement set).
RANDOM_OFF_RE = re.compile(
    r"""
    (?:^|[\s,;])
    (?P<key>NEXUS_SECURITY_RANDOMPASSWORD
        |nexus\.security\.randompassword)
    \s*[:=]\s*
    (?P<val>"?(?:false|no|0)"?)
    """,
    re.VERBOSE | re.IGNORECASE,
)

# 3. COPY / ADD / mount of admin.password into a baked image.
COPY_ADMINPW_RE = re.compile(
    r"""
    ^\s*
    (?:COPY|ADD)\s+
    (?:--[^\s]+\s+)*                         # optional --chown=, etc.
    \S*admin\.password\b
    """,
    re.VERBOSE | re.IGNORECASE,
)
COMPOSE_MOUNT_RE = re.compile(
    r"^\s*-\s+\S*admin\.password\s*:\s*/nexus-data/admin\.password",
    re.IGNORECASE,
)

# 4. REST change-password call with trivial body.
REST_CHANGEPW_RE = re.compile(
    r"/service/rest/v1/security/users/admin/change-password",
    re.IGNORECASE,
)
# Body extraction: -d 'admin123', --data "admin123", or JSON value.
BODY_QUOTED_RE = re.compile(r"""(?:-d|--data(?:-raw)?)\s+["']([^"']+)["']""")
JSON_PW_RE = re.compile(r'"password"\s*:\s*"([^"]+)"')


def _strip(value: str) -> str:
    v = value.strip()
    if (v.startswith('"') and v.endswith('"')) or (
        v.startswith("'") and v.endswith("'")
    ):
        v = v[1:-1]
    return v


def _is_placeholder(value: str) -> bool:
    v = value.strip()
    if not v:
        return True
    return any(
        marker in v
        for marker in ("${", "$(", "<<", "{{", "%(", "%ENV%")
    )


def scan(source: str) -> List[Tuple[int, str]]:
    findings: List[Tuple[int, str]] = []
    if SUPPRESS.search(source):
        return findings

    lines = source.splitlines()
    has_random_off = False
    has_real_initial = False
    random_off_line = 0

    for i, raw in enumerate(lines, start=1):

        # 1. initial password set to trivial
        for m in INITIAL_PW_RE.finditer(raw):
            val = _strip(m.group("val"))
            if _is_placeholder(val):
                has_real_initial = True
                continue
            if val.lower() in TRIVIAL:
                findings.append((
                    i,
                    f"{m.group('key')} set to trivial/default value '{val}' — "
                    f"Nexus admin password must be unique per environment",
                ))
            else:
                has_real_initial = True

        # 2. randompassword disabled?
        if RANDOM_OFF_RE.search(raw):
            has_random_off = True
            if random_off_line == 0:
                random_off_line = i

        # 3. baking admin.password into the image
        if COPY_ADMINPW_RE.search(raw):
            findings.append((
                i,
                "Dockerfile bakes /nexus-data/admin.password into the image — "
                "the bootstrap secret leaks via image layer",
            ))
        if COMPOSE_MOUNT_RE.search(raw):
            findings.append((
                i,
                "compose mounts a static admin.password into /nexus-data/ — "
                "treat as a hard-coded admin credential",
            ))

        # 4. REST change-password to trivial value
        if REST_CHANGEPW_RE.search(raw):
            # Look 4 lines back and 3 forward for a body / payload —
            # `curl ... -d 'admin123' ... <URL>` puts body before URL.
            lo = max(0, i - 5)
            hi = min(i + 3, len(lines))
            window = "\n".join(lines[lo:hi])
            candidates: List[str] = []
            candidates.extend(BODY_QUOTED_RE.findall(window))
            candidates.extend(JSON_PW_RE.findall(window))
            for cand in candidates:
                if _is_placeholder(cand):
                    continue
                if cand.lower() in TRIVIAL:
                    findings.append((
                        i,
                        f"REST change-password call sets admin password to "
                        f"trivial value '{cand}'",
                    ))
                    break

    # 5. randompassword disabled with no real replacement → finding.
    if has_random_off and not has_real_initial:
        findings.append((
            random_off_line,
            "nexus.security.randompassword=false without a paired non-trivial "
            "nexus.security.initialPassword — Nexus will fall back to the "
            "static default 'admin123'",
        ))

    findings.sort(key=lambda x: x[0])
    return findings


def scan_paths(paths: Iterable[Path]) -> int:
    bad_files = 0
    targets: List[Path] = []
    for path in paths:
        if path.is_dir():
            for ext in (
                "*.yaml",
                "*.yml",
                "*.env",
                "*.sh",
                "*.groovy",
                "Dockerfile",
                "docker-compose*",
                "*.conf",
                "*.properties",
            ):
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
