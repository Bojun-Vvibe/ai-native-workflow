#!/usr/bin/env python3
"""Detect SonarQube deployments / provisioning artifacts that leave
the built-in ``admin`` account on its default password (``admin``).

Background
==========

SonarQube ships exactly one bootstrap account: username ``admin``,
password ``admin``. The first-run UI prompts an operator to change
it, but headless / containerised deployments routinely skip that
step. The Sonar Web API at ``/api/system/change_log_level``,
``/api/settings/set``, ``/api/projects/create``, ``/api/users/*``,
and the plugin upload surface at ``/deploy/plugins`` then accept
``Basic YWRtaW46YWRtaW4=`` and the host is fully owned (plugins
are JARs that run inside the SonarQube JVM).

LLM-generated provisioning artifacts that re-introduce the default
credential typically look like one of:

  * a `docker-compose.yml` / Helm values file with
    `SONAR_WEB_SYSTEMPASSCODE` unset and an `admin/admin` curl in
    the README,
  * a `curl -u admin:admin https://sonar.example/api/...` line in a
    bootstrap script,
  * an ``.env`` / k8s ``ConfigMap`` setting
    ``SONAR_ADMIN_PASSWORD=admin``,
  * a `sonar-scanner` invocation passing
    ``-Dsonar.login=admin -Dsonar.password=admin`` (or the
    equivalent ``SONAR_TOKEN`` set to the literal string ``admin``),
  * an HTTP ``Authorization: Basic YWRtaW46YWRtaW4=`` header
    (base64 of ``admin:admin``) hard-coded into config.

What this detector flags
========================

Any of the following patterns, on a single non-comment line:

  1. ``-u admin:admin`` / ``--user admin:admin`` (curl, httpie style).
  2. ``SONAR_ADMIN_PASSWORD = admin`` (env / dotenv / yaml / ini).
  3. ``sonar.login=admin`` paired with ``sonar.password=admin``
     anywhere in the same file (sonar-scanner properties).
  4. ``Authorization: Basic YWRtaW46YWRtaW4=`` (base64 of
     ``admin:admin``, with optional surrounding quotes).
  5. ``SONAR_TOKEN=admin`` (literal string ``admin`` in place of a
     real token).

A file containing the marker ``sonarqube-default-admin-allowed``
is treated as suppressed.

Usage
=====

    python3 detector.py path/to/file [more files...]

Exit code equals the number of findings; ``0`` means clean.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

SUPPRESS_MARK = "sonarqube-default-admin-allowed"

# 1. curl -u admin:admin  /  curl --user admin:admin
CURL_USERPASS_RE = re.compile(
    r"""(?:^|[\s'"`])(?:-u|--user)[\s=]+['"]?admin:admin['"]?(?=$|[\s'"`&|;])""",
    re.IGNORECASE,
)

# 2. SONAR_ADMIN_PASSWORD = admin (env, dotenv, yaml-ish, ini)
SONAR_ADMIN_PW_RE = re.compile(
    r"""(?im)^\s*SONAR_ADMIN_PASSWORD\s*[:=]\s*['"]?admin['"]?\s*$""",
)

# 3a. sonar-scanner properties: literal `admin` for login or password.
SONAR_LOGIN_RE = re.compile(
    r"""(?im)^\s*sonar\.login\s*=\s*admin\s*$""",
)
SONAR_PASSWORD_RE = re.compile(
    r"""(?im)^\s*sonar\.password\s*=\s*admin\s*$""",
)

# 4. Authorization: Basic YWRtaW46YWRtaW4=  (base64("admin:admin"))
BASIC_AUTH_HEADER_RE = re.compile(
    r"""Authorization\s*:\s*['"]?Basic\s+YWRtaW46YWRtaW4=['"]?""",
    re.IGNORECASE,
)

# 5. SONAR_TOKEN=admin (literal "admin" used as token)
SONAR_TOKEN_RE = re.compile(
    r"""(?im)^\s*SONAR_TOKEN\s*[:=]\s*['"]?admin['"]?\s*$""",
)

# Strip common single-line comments so we don't trip on examples in docs.
COMMENT_LINE_RES = [
    re.compile(r"(?m)^\s*#.*$"),         # shell / yaml / ini / dotenv
    re.compile(r"(?m)^\s*//.*$"),        # js / java / go
    re.compile(r"(?m)^\s*--.*$"),        # sql / lua
    re.compile(r"(?m)^\s*;.*$"),         # ini variant
]
BLOCK_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)


def strip_comments(text: str) -> str:
    text = BLOCK_COMMENT_RE.sub("", text)
    for rx in COMMENT_LINE_RES:
        text = rx.sub("", text)
    return text


def scan(path: Path) -> list[str]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return [f"{path}: cannot read ({exc})"]

    if SUPPRESS_MARK in text:
        return []

    src = strip_comments(text)
    findings: list[str] = []

    if CURL_USERPASS_RE.search(src):
        findings.append(f"{path}: curl uses default admin:admin basic auth")
    if SONAR_ADMIN_PW_RE.search(src):
        findings.append(f"{path}: SONAR_ADMIN_PASSWORD set to default 'admin'")
    if SONAR_LOGIN_RE.search(src) and SONAR_PASSWORD_RE.search(src):
        findings.append(
            f"{path}: sonar.login=admin paired with sonar.password=admin"
        )
    if BASIC_AUTH_HEADER_RE.search(src):
        findings.append(
            f"{path}: Authorization header carries base64(admin:admin)"
        )
    if SONAR_TOKEN_RE.search(src):
        findings.append(f"{path}: SONAR_TOKEN set to literal 'admin'")

    return findings


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: detector.py <file> [<file>...]", file=sys.stderr)
        return 0
    findings: list[str] = []
    for arg in argv[1:]:
        findings.extend(scan(Path(arg)))
    for f in findings:
        print(f)
    return len(findings)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
