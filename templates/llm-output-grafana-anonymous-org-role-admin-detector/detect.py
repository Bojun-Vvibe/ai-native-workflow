#!/usr/bin/env python3
"""
llm-output-grafana-anonymous-org-role-admin-detector

Flags Grafana deployments where the **anonymous auth** provider is
enabled AND the anonymous user is granted the `Admin` (or `Editor`)
org role. The combination means anyone who can reach the Grafana HTTP
endpoint -- with no credentials at all -- can:

  * read every dashboard, every datasource (including the configured
    SQL / Prometheus credentials in plaintext via the API),
  * create / edit / delete dashboards and alerts (Editor),
  * add new datasources, install plugins, manage users, change org
    settings, and (in newer Grafana) execute arbitrary SQL against
    bound datasources via the query API (Admin).

`auth.anonymous` was designed for **public read-only kiosks** (role =
`Viewer`). Promoting the anonymous principal to `Editor` or `Admin`
turns the Grafana instance into an unauthenticated control plane for
whatever it is wired up to.

Maps to:
  - CWE-862: Missing Authorization
  - CWE-1188: Insecure Default Initialization of Resource
  - CWE-284: Improper Access Control
  - OWASP A01:2021 Broken Access Control

Why LLMs ship this
------------------
Tutorials say "to make Grafana public, set `[auth.anonymous] enabled =
true` and bump `org_role` so people can edit". The model copies that
into a Helm values file or Docker env block without distinguishing
"public-read kiosk" from "give the internet root on our metrics
stack".

Heuristic
---------
We look at three concrete config surfaces:

1. **Grafana ini / config files** (`grafana.ini`, `*.ini`, `*.conf`,
   `*.cfg`) -- INI sections. We require both:
     - `[auth.anonymous]` block enabling the provider
       (`enabled = true` / `enabled=1`), AND
     - in the same block, `org_role` set to `Admin` or `Editor`
       (case-insensitive).

2. **Environment variables** (Dockerfile / docker-compose / k8s /
   systemd / shell): the official Grafana image maps
   `GF_<SECTION>_<KEY>` -> ini key. We flag the pair:
     - `GF_AUTH_ANONYMOUS_ENABLED=true`, AND
     - `GF_AUTH_ANONYMOUS_ORG_ROLE=Admin` or `=Editor`,
   when both appear in the same file.

3. **Helm values / generic YAML** under a `grafana:` or
   `grafana.ini:` mapping that nests `auth.anonymous` with both
   `enabled: true` and `org_role: Admin|Editor`.

A finding is emitted with the line number of the offending `org_role`
assignment (the more specific of the two), so reviewers land on the
escalation, not just the toggle.

Stdlib-only. Walks dirs, scans `*.ini`, `*.conf`, `*.cfg`, `*.yaml`,
`*.yml`, `*.env`, `*.sh`, `*.bash`, `*.service`, `Dockerfile*`, and
`docker-compose.*`.

Exit codes: 0 = clean, 1 = findings printed, 2 = usage error.
"""

from __future__ import annotations

import os
import re
import sys
from typing import Iterable, List, Tuple

_BAD_ROLES = ("admin", "editor")

# INI: detect `[auth.anonymous]` section header.
_INI_AUTH_ANON_HEADER = re.compile(r"""^\s*\[\s*auth\.anonymous\s*\]\s*$""", re.IGNORECASE)
_INI_ANY_HEADER = re.compile(r"""^\s*\[[^\]]+\]\s*$""")
_INI_ENABLED_TRUE = re.compile(r"""^\s*enabled\s*=\s*(?:true|1|yes|on)\s*(?:[#;].*)?$""", re.IGNORECASE)
_INI_ORG_ROLE = re.compile(r"""^\s*org_role\s*=\s*([A-Za-z]+)\s*(?:[#;].*)?$""", re.IGNORECASE)

# Env-var form: GF_AUTH_ANONYMOUS_ENABLED / GF_AUTH_ANONYMOUS_ORG_ROLE.
# Match key=value, key: value (compose), and ENV / -e prefixes.
_ENV_ENABLED = re.compile(
    r"""\bGF_AUTH_ANONYMOUS_ENABLED\b\s*[:=]\s*["']?(true|1|yes|on)["']?""",
    re.IGNORECASE,
)
_ENV_ROLE = re.compile(
    r"""\bGF_AUTH_ANONYMOUS_ORG_ROLE\b\s*[:=]\s*["']?([A-Za-z]+)["']?""",
    re.IGNORECASE,
)

# YAML-ish: flag lines like `org_role: Admin` that sit under an
# `anonymous:` key (we use a small state machine, see scan_yaml).
_YAML_ANON_KEY = re.compile(r"""^(\s*)(?:auth\.)?anonymous\s*:\s*(?:#.*)?$""")
_YAML_ENABLED = re.compile(r"""^(\s*)enabled\s*:\s*["']?(true|1|yes|on)["']?\s*(?:#.*)?$""", re.IGNORECASE)
_YAML_ROLE = re.compile(r"""^(\s*)org_role\s*:\s*["']?([A-Za-z]+)["']?\s*(?:#.*)?$""", re.IGNORECASE)
_YAML_DEDENT_KEY = re.compile(r"""^(\s*)[A-Za-z0-9_.-]+\s*:""")

_COMMENT_LINE = re.compile(r"""^\s*[#;]""")


def scan_ini(text: str, path: str) -> List[str]:
    findings: List[str] = []
    in_anon = False
    enabled_line = -1
    role_line = -1
    role_value = ""
    for lineno, raw in enumerate(text.splitlines(), start=1):
        if _INI_AUTH_ANON_HEADER.match(raw):
            in_anon = True
            enabled_line = -1
            role_line = -1
            role_value = ""
            continue
        if in_anon and _INI_ANY_HEADER.match(raw):
            # Section ended without satisfying both conditions.
            in_anon = False
            enabled_line = -1
            role_line = -1
            role_value = ""
            # Re-check this line in case it's the next anon header
            # (cannot legally repeat, but be defensive).
            if _INI_AUTH_ANON_HEADER.match(raw):
                in_anon = True
            continue
        if not in_anon:
            continue
        if _COMMENT_LINE.match(raw):
            continue
        if _INI_ENABLED_TRUE.match(raw):
            enabled_line = lineno
        m = _INI_ORG_ROLE.match(raw)
        if m and m.group(1).lower() in _BAD_ROLES:
            role_line = lineno
            role_value = m.group(1)
        if enabled_line > 0 and role_line > 0:
            findings.append(
                f"{path}:{role_line}: grafana [auth.anonymous] enabled "
                f"(line {enabled_line}) with org_role={role_value} "
                f"(CWE-862/CWE-1188): unauthenticated {role_value} access"
            )
            # Reset to avoid duplicate emission on later lines in same section.
            enabled_line = -1
            role_line = -1
    return findings


def scan_env(text: str, path: str) -> List[str]:
    findings: List[str] = []
    enabled_line = -1
    role_line = -1
    role_value = ""
    for lineno, raw in enumerate(text.splitlines(), start=1):
        if _COMMENT_LINE.match(raw):
            continue
        if _ENV_ENABLED.search(raw):
            enabled_line = lineno
        m = _ENV_ROLE.search(raw)
        if m and m.group(1).lower() in _BAD_ROLES:
            role_line = lineno
            role_value = m.group(1)
    if enabled_line > 0 and role_line > 0:
        findings.append(
            f"{path}:{role_line}: GF_AUTH_ANONYMOUS_ENABLED=true "
            f"(line {enabled_line}) and GF_AUTH_ANONYMOUS_ORG_ROLE="
            f"{role_value} -> unauthenticated {role_value} access "
            f"(CWE-862/CWE-1188)"
        )
    return findings


def scan_yaml(text: str, path: str) -> List[str]:
    findings: List[str] = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        m = _YAML_ANON_KEY.match(lines[i])
        if not m:
            i += 1
            continue
        base_indent = len(m.group(1))
        # Walk forward while indent > base_indent.
        enabled_line = -1
        role_line = -1
        role_value = ""
        j = i + 1
        while j < len(lines):
            line = lines[j]
            if line.strip() == "" or _COMMENT_LINE.match(line):
                j += 1
                continue
            # Detect dedent (sibling/parent key).
            md = _YAML_DEDENT_KEY.match(line)
            if md and len(md.group(1)) <= base_indent:
                break
            me = _YAML_ENABLED.match(line)
            if me:
                enabled_line = j + 1
            mr = _YAML_ROLE.match(line)
            if mr and mr.group(2).lower() in _BAD_ROLES:
                role_line = j + 1
                role_value = mr.group(2)
            j += 1
        if enabled_line > 0 and role_line > 0:
            findings.append(
                f"{path}:{role_line}: grafana anonymous: block enabled "
                f"(line {enabled_line}) with org_role={role_value} "
                f"(CWE-862/CWE-1188): unauthenticated {role_value} access"
            )
        i = j if j > i else i + 1
    return findings


def scan(path: str) -> List[str]:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
    except OSError as e:
        sys.stderr.write(f"warn: cannot read {path}: {e}\n")
        return []
    low = path.lower()
    out: List[str] = []
    if low.endswith((".ini", ".conf", ".cfg")):
        out.extend(scan_ini(text, path))
    if low.endswith((".yaml", ".yml")):
        # Helm values may inline ini-style under `grafana.ini: |` blocks,
        # so try both.
        out.extend(scan_yaml(text, path))
        out.extend(scan_ini(text, path))
        out.extend(scan_env(text, path))
    if low.endswith((".env", ".sh", ".bash", ".service")):
        out.extend(scan_env(text, path))
    base = os.path.basename(low)
    if base.startswith("dockerfile") or base.startswith("docker-compose") \
            or low.endswith(".dockerfile"):
        out.extend(scan_env(text, path))
        if base.startswith("docker-compose"):
            out.extend(scan_yaml(text, path))
    return out


_TARGET_NAMES = ("dockerfile", "docker-compose.yml", "docker-compose.yaml")
_TARGET_EXTS = (".ini", ".conf", ".cfg", ".yaml", ".yml", ".env",
                ".sh", ".bash", ".service", ".dockerfile")


def iter_paths(roots: Iterable[str]) -> Iterable[str]:
    for r in roots:
        if os.path.isdir(r):
            for dp, _dn, fn in os.walk(r):
                for f in fn:
                    low = f.lower()
                    if low in _TARGET_NAMES or low.startswith("dockerfile") \
                            or low.startswith("docker-compose"):
                        yield os.path.join(dp, f)
                    elif low.endswith(_TARGET_EXTS):
                        yield os.path.join(dp, f)
        else:
            yield r


def main(argv: List[str]) -> int:
    if len(argv) < 2:
        sys.stderr.write("usage: detect.py <file-or-dir> [more...]\n")
        return 2
    any_finding = False
    for path in iter_paths(argv[1:]):
        for line in scan(path):
            print(line)
            any_finding = True
    return 1 if any_finding else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
