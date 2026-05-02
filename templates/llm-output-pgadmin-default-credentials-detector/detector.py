#!/usr/bin/env python3
"""Detect pgAdmin 4 deployments that ship with the documented default
admin credentials, the well-known placeholder email, or hard-coded
weak password literals in compose / env / Kubernetes / Dockerfile /
config files.

Background. The pgAdmin 4 container image requires
``PGADMIN_DEFAULT_EMAIL`` and ``PGADMIN_DEFAULT_PASSWORD`` to boot.
The upstream README uses ``admin@admin.com`` / ``admin`` as
placeholders, which LLMs routinely paste verbatim into production
compose files. Because pgAdmin is a credential vault for every
Postgres server it connects to, those credentials grant any reachable
caller the full set of downstream database passwords — escalating a
"just internal UI" exposure into compromise of every managed cluster.

This detector is intentionally orthogonal to TLS / bind-address /
network-policy detectors: weak credentials are bad regardless of the
network shape, because internal lateral movement is the assumed
threat model for a credential-vault service.

What's checked (per file):
  - ``PGADMIN_DEFAULT_EMAIL`` set to one of the well-known
    placeholders (``admin@admin.com``, ``admin@example.com``,
    ``user@domain.com``, ``pgadmin@pgadmin.org``,
    ``postgres@postgres.com``).
  - ``PGADMIN_DEFAULT_PASSWORD`` set to a literal in the weak-password
    set (``admin``, ``pgadmin``, ``password``, ``changeme``, ``root``,
    ``postgres``, ``12345``, ``12345678``, ``letmein``, ``qwerty``).
  - ``MASTER_PASSWORD = '...'`` in ``config_local.py`` set to the
    same weak set.
  - Same checks against Dockerfile ``ENV ... ...`` lines and YAML
    ``- name: PGADMIN_DEFAULT_PASSWORD\\n  value: ...``.

Findings are reported per line.

CWE refs:
  - CWE-798: Use of Hard-coded Credentials
  - CWE-521: Weak Password Requirements
  - CWE-1392: Use of Default Credentials

False-positive surface:
  - Suppress per file with a comment ``# pgadmin-default-allowed``.
  - Env-var / secret references (``${VAR}``, ``valueFrom``,
    ``secretKeyRef``) are treated as safe.
  - Only exact weak-password-set matches trigger; long random strings
    that contain ``admin`` as a prefix are not flagged.

Usage:
    python3 detector.py <path> [<path> ...]

Exit code: number of files with at least one finding (capped at 255).
Stdout:    ``<file>:<line>:<reason>``.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Iterable, List, Tuple

SUPPRESS = re.compile(r"#\s*pgadmin-default-allowed")

PLACEHOLDER_EMAILS = {
    "admin@admin.com",
    "admin@example.com",
    "admin@example.org",
    "user@domain.com",
    "pgadmin@pgadmin.org",
    "postgres@postgres.com",
    "test@test.com",
}

WEAK_PASSWORDS = {
    "admin",
    "pgadmin",
    "password",
    "passwd",
    "changeme",
    "change-me",
    "root",
    "postgres",
    "12345",
    "123456",
    "1234567",
    "12345678",
    "letmein",
    "qwerty",
    "secret",
}

# Matches both "KEY=value" (env file / Dockerfile ARG) and
# "KEY value" (Dockerfile ENV) and YAML "KEY: value".
ENV_EMAIL_RE = re.compile(
    r"""(?ix)
    (?:^|\s|-|"|')
    PGADMIN_DEFAULT_EMAIL
    \s*[:=\s]\s*
    (?P<val>[^\s"',}\]]+)
    """,
)
ENV_PASSWORD_RE = re.compile(
    r"""(?ix)
    (?:^|\s|-|"|')
    PGADMIN_DEFAULT_PASSWORD
    \s*[:=\s]\s*
    (?P<val>[^\s"',}\]]+)
    """,
)

# YAML env-list shape:
#   - name: PGADMIN_DEFAULT_PASSWORD
#     value: admin
YAML_NAME_RE = re.compile(
    r"""^\s*-\s*name\s*:\s*['"]?(?P<name>PGADMIN_DEFAULT_(?:EMAIL|PASSWORD))['"]?\s*$""",
)
YAML_VALUE_RE = re.compile(
    r"""^\s*value\s*:\s*['"]?(?P<val>[^'"#\s][^#]*?)['"]?\s*(?:#.*)?$""",
)
YAML_VALUEFROM_RE = re.compile(r"^\s*valueFrom\s*:")

# config_local.py: MASTER_PASSWORD = 'admin'
PY_MASTER_RE = re.compile(
    r"""^\s*MASTER_PASSWORD\s*=\s*['"](?P<val>[^'"]*)['"]""",
)


def _is_secret_ref(val: str) -> bool:
    v = val.strip().strip("'\"")
    if not v:
        return False
    if v.startswith("$") or "${" in v or "$(" in v:
        return True
    if v.startswith("valueFrom") or v.startswith("secretKeyRef"):
        return True
    return False


def _check_email(val: str) -> bool:
    v = val.strip().strip("'\"").lower()
    return v in PLACEHOLDER_EMAILS


def _check_password(val: str) -> bool:
    v = val.strip().strip("'\"")
    if _is_secret_ref(v):
        return False
    return v.lower() in WEAK_PASSWORDS


def scan(source: str) -> List[Tuple[int, str]]:
    findings: List[Tuple[int, str]] = []
    if SUPPRESS.search(source):
        return findings

    # JSON code path: try to parse and walk recursively.
    stripped_src = source.lstrip()
    if stripped_src.startswith("{") or stripped_src.startswith("["):
        try:
            data = json.loads(source)
        except (json.JSONDecodeError, ValueError):
            data = None
        if data is not None:
            def walk(node):
                if isinstance(node, dict):
                    for k, v in node.items():
                        if isinstance(k, str):
                            ku = k.upper()
                            if ku == "PGADMIN_DEFAULT_EMAIL" and isinstance(v, str) and _check_email(v):
                                findings.append((
                                    1,
                                    f"PGADMIN_DEFAULT_EMAIL is the documented placeholder {v.lower()}",
                                ))
                            elif ku == "PGADMIN_DEFAULT_PASSWORD" and isinstance(v, str) and _check_password(v):
                                findings.append((
                                    1,
                                    f"PGADMIN_DEFAULT_PASSWORD is the documented default '{v.lower()}'",
                                ))
                        walk(v)
                elif isinstance(node, list):
                    for item in node:
                        walk(item)
            walk(data)
            return findings

    lines = source.splitlines()

    # Pass 1: line-local KEY=VALUE / KEY: value patterns.
    for i, raw in enumerate(lines, start=1):
        line = raw
        # Skip pure-comment lines (shell `#`, Dockerfile `#`).
        stripped = line.lstrip()
        if stripped.startswith("#") or stripped.startswith("//"):
            continue

        for m in ENV_EMAIL_RE.finditer(line):
            val = m.group("val")
            if _is_secret_ref(val):
                continue
            if _check_email(val):
                findings.append((
                    i,
                    f"PGADMIN_DEFAULT_EMAIL is the documented placeholder "
                    f"{val.strip().strip(chr(34) + chr(39)).lower()}",
                ))

        for m in ENV_PASSWORD_RE.finditer(line):
            val = m.group("val")
            if _is_secret_ref(val):
                continue
            if _check_password(val):
                findings.append((
                    i,
                    f"PGADMIN_DEFAULT_PASSWORD is the documented default "
                    f"'{val.strip().strip(chr(34) + chr(39)).lower()}'",
                ))

        m = PY_MASTER_RE.match(line)
        if m and _check_password(m.group("val")):
            findings.append((
                i,
                f"MASTER_PASSWORD set to weak literal "
                f"'{m.group('val').lower()}'",
            ))

    # Pass 2: YAML env-list shape spanning two lines.
    i = 0
    while i < len(lines):
        m_name = YAML_NAME_RE.match(lines[i])
        if m_name:
            name = m_name.group("name").upper()
            # Look ahead a few lines for `value:` or `valueFrom:`.
            for j in range(i + 1, min(i + 4, len(lines))):
                if YAML_VALUEFROM_RE.match(lines[j]):
                    break
                m_val = YAML_VALUE_RE.match(lines[j])
                if m_val:
                    val = m_val.group("val")
                    if name.endswith("EMAIL") and _check_email(val):
                        findings.append((
                            j + 1,
                            f"PGADMIN_DEFAULT_EMAIL is the documented placeholder "
                            f"{val.strip().lower()}",
                        ))
                    elif name.endswith("PASSWORD") and _check_password(val):
                        findings.append((
                            j + 1,
                            f"PGADMIN_DEFAULT_PASSWORD is the documented default "
                            f"'{val.strip().lower()}'",
                        ))
                    break
        i += 1

    # Deduplicate.
    seen = set()
    out: List[Tuple[int, str]] = []
    for f in findings:
        if f in seen:
            continue
        seen.add(f)
        out.append(f)
    return out


def scan_paths(paths: Iterable[Path]) -> int:
    bad_files = 0
    targets: List[Path] = []
    for path in paths:
        if path.is_dir():
            for ext in (
                "*.yaml", "*.yml", "*.env", "*.conf",
                "*.py", "*.ini", "*.toml", "*.json",
                "Dockerfile", "*.sh",
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
