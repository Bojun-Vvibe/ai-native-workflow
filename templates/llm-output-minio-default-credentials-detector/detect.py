#!/usr/bin/env python3
"""
llm-output-minio-default-credentials-detector

Flags configurations that run a MinIO (S3-compatible object store)
server using the **default `minioadmin` / `minioadmin` root
credentials** -- or, more generally, with weak/empty values for the
root access key & secret env vars.

The MinIO server's first-boot defaults are documented as
`minioadmin` for both `MINIO_ROOT_USER` and `MINIO_ROOT_PASSWORD`
(historically `MINIO_ACCESS_KEY` / `MINIO_SECRET_KEY`). Leaving them
unchanged in production hands an attacker full bucket
read/write/delete and -- because MinIO supports running shell-out
notifications and admin policies -- often a path to host pivot.

Patterns flagged
----------------

1. Shell / Dockerfile / compose / k8s manifests setting any of:

       MINIO_ROOT_USER=minioadmin
       MINIO_ROOT_PASSWORD=minioadmin
       MINIO_ACCESS_KEY=minioadmin
       MINIO_SECRET_KEY=minioadmin

   ...or any of the same keys set to a known-weak value
   (`admin`, `password`, `12345`, empty string, etc.), with
   surrounding quotes optional.

2. Helm `values.yaml` style:

       rootUser: minioadmin
       rootPassword: minioadmin

3. `mc alias set` commands using `minioadmin minioadmin`.

What we do NOT flag
-------------------
- Local development / test scripts that *also* contain a comment
  like `# DEV ONLY` on the same line are still flagged -- the goal
  is to surface every occurrence; humans decide.
- `MINIO_ROOT_PASSWORD_FILE=...` (file-mounted secret) is not flagged.
- Values referencing env interpolation (`${SECRET_PASS}`,
  `{{ .Values.x }}`, `$(cat ...)`) are not flagged.

References
----------
- MinIO docs, "Root user / root password".
- CWE-798: Use of Hard-coded Credentials.
- CWE-1188: Insecure Default Initialization of Resource.
- OWASP A07:2021 Identification and Authentication Failures.

Stdlib-only. Scans `*.sh`, `*.bash`, `*.yaml`, `*.yml`, `*.ini`,
`*.conf`, `*.cfg`, `Dockerfile*`, `docker-compose.*`.

Exit codes: 0 = clean, 1 = findings, 2 = usage error.
"""

from __future__ import annotations

import os
import re
import sys
from typing import Iterable, List

_ENV_KEYS = (
    "MINIO_ROOT_USER",
    "MINIO_ROOT_PASSWORD",
    "MINIO_ACCESS_KEY",
    "MINIO_SECRET_KEY",
)
_PASS_KEYS = ("MINIO_ROOT_PASSWORD", "MINIO_SECRET_KEY")
_USER_KEYS = ("MINIO_ROOT_USER", "MINIO_ACCESS_KEY")

_WEAK_PASSWORDS = {
    "minioadmin", "admin", "password", "changeme", "changeme!",
    "root", "12345", "123456", "letmein", "secret", "test",
    "default", "minio", "minio123",
}
_WEAK_USERS = {"minioadmin", "admin", "root", "minio"}

_COMMENT_LINE = re.compile(r"""^\s*[#;]""")
_INTERP = re.compile(r"""\$\{|\$\(|\{\{|<<""")

# KEY=VALUE  (shell / dockerfile ENV / dotenv-like)
_ENV_ASSIGN = re.compile(
    r"""\b(MINIO_(?:ROOT_USER|ROOT_PASSWORD|ACCESS_KEY|SECRET_KEY))"""
    r"""\s*[=:]\s*["']?([^"'#\s]*)["']?""",
)
# Dockerfile: ENV KEY VALUE   (space-separated form)
_DOCKER_ENV = re.compile(
    r"""^\s*ENV\s+(MINIO_(?:ROOT_USER|ROOT_PASSWORD|ACCESS_KEY|SECRET_KEY))"""
    r"""\s+["']?([^"'\s]*)["']?\s*$""",
    re.IGNORECASE,
)

# YAML key: value form for Helm values.yaml-like files.
_YAML_KV = re.compile(
    r"""^\s*(rootUser|rootPassword|accessKey|secretKey)\s*:\s*"""
    r"""["']?([^"'#\n]*?)["']?\s*(?:#.*)?$""",
)

# `mc alias set <name> <url> <user> <pass>`
_MC_ALIAS = re.compile(
    r"""\bmc\s+(?:--[^\s]+\s+)*alias\s+set\s+\S+\s+\S+\s+(\S+)\s+(\S+)""",
)


def _is_interp(value: str) -> bool:
    return bool(_INTERP.search(value))


def _flag_value(key: str, value: str) -> bool:
    if _is_interp(value):
        return False
    if key in _PASS_KEYS or key in ("rootPassword", "secretKey"):
        if value == "":
            return True
        return value.lower() in _WEAK_PASSWORDS
    if key in _USER_KEYS or key in ("rootUser", "accessKey"):
        if value == "":
            return False  # empty user alone is not a credential leak
        return value.lower() in _WEAK_USERS
    return False


def scan_lines(text: str, path: str) -> List[str]:
    findings: List[str] = []
    is_yaml = path.lower().endswith((".yaml", ".yml"))
    is_dockerfile = "dockerfile" in os.path.basename(path).lower()

    for lineno, raw in enumerate(text.splitlines(), start=1):
        if _COMMENT_LINE.match(raw):
            continue

        # Dockerfile ENV K V form first.
        if is_dockerfile:
            dm = _DOCKER_ENV.match(raw)
            if dm:
                k = dm.group(1).upper()
                v = dm.group(2)
                if _flag_value(k, v):
                    findings.append(
                        f"{path}:{lineno}: {k}={v or '<empty>'} "
                        f"(weak/default MinIO credential, CWE-798/CWE-1188): "
                        f"{raw.strip()[:160]}"
                    )

        # KEY=VALUE form (shell, dotenv, compose env list, k8s env value).
        for m in _ENV_ASSIGN.finditer(raw):
            k = m.group(1).upper()
            v = m.group(2)
            if _flag_value(k, v):
                findings.append(
                    f"{path}:{lineno}: {k}={v or '<empty>'} "
                    f"(weak/default MinIO credential, CWE-798/CWE-1188): "
                    f"{raw.strip()[:160]}"
                )

        # Helm-style yaml.
        if is_yaml:
            ym = _YAML_KV.match(raw)
            if ym:
                k = ym.group(1)
                v = ym.group(2).strip()
                if _flag_value(k, v):
                    findings.append(
                        f"{path}:{lineno}: {k}: {v or '<empty>'} "
                        f"(weak/default MinIO credential, CWE-798/CWE-1188): "
                        f"{raw.strip()[:160]}"
                    )

        # mc alias set ... user pass
        am = _MC_ALIAS.search(raw)
        if am:
            user, pw = am.group(1), am.group(2)
            if not _is_interp(user) and not _is_interp(pw):
                if pw.lower() in _WEAK_PASSWORDS \
                        or user.lower() in _WEAK_USERS:
                    findings.append(
                        f"{path}:{lineno}: `mc alias set` uses "
                        f"weak/default MinIO credentials "
                        f"({user}/{pw}) -> CWE-798: "
                        f"{raw.strip()[:160]}"
                    )
    return findings


_TARGET_EXTS = (".sh", ".bash", ".yaml", ".yml", ".ini", ".conf",
                ".cfg", ".service")


def _is_target(path: str) -> bool:
    low = path.lower()
    base = os.path.basename(low)
    if base.startswith("dockerfile") or base.startswith("docker-compose"):
        return True
    if "dockerfile" in base:
        return True
    return low.endswith(_TARGET_EXTS)


def scan(path: str) -> List[str]:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
    except OSError as e:
        sys.stderr.write(f"warn: cannot read {path}: {e}\n")
        return []
    if not _is_target(path):
        return []
    # Cheap pre-filter.
    low_text = text
    if "MINIO" not in low_text and "minio" not in low_text \
            and "rootUser" not in low_text and "rootPassword" not in low_text \
            and "accessKey" not in low_text and "secretKey" not in low_text \
            and " mc " not in low_text and "mc alias" not in low_text:
        return []
    return scan_lines(text, path)


def iter_paths(roots: Iterable[str]) -> Iterable[str]:
    for r in roots:
        if os.path.isdir(r):
            for dp, _dn, fn in os.walk(r):
                for f in fn:
                    p = os.path.join(dp, f)
                    if _is_target(p):
                        yield p
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
