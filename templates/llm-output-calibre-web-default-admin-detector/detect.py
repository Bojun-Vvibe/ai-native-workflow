#!/usr/bin/env python3
"""
llm-output-calibre-web-default-admin-detector

Flags Calibre-Web (janeczku/calibre-web) deployments that ship with
the documented first-run default credentials `admin` / `admin123`
without rotation, or that pre-seed those credentials into the
config / env / SQL bootstrap. Calibre-Web's admin role grants:
edit/delete books, run shell-style "convert" subprocess commands via
the optional `UPLOAD` and `CONVERTERTOOL` settings, configure SMTP
(credential exfiltration), and create new users. Shipping the
default admin/admin123 on a public bind is account takeover plus a
known-good path to RCE through the converter pipeline.

Maps to:
- CWE-798: Use of Hard-coded Credentials.
- CWE-521: Weak Password Requirements.
- CWE-1392: Use of Default Credentials.

Stdlib-only. Reads files passed on argv (recurses into dirs and picks
*.json, *.yaml, *.yml, *.conf, *.ini, *.env, *.sh, *.bash, *.sql,
*.service, Dockerfile, docker-compose.*).

Exit codes: 0 = no findings, 1 = findings, 2 = usage error.

Heuristic
---------
We flag, outside `#` / `;` / `//` comment lines, any of:

1. Env-var pair that pre-seeds the documented default admin
   password: `CALIBRE_WEB_ADMIN_PASSWORD=admin123` (or the
   linuxserver/calibre-web override `ADMIN_PASSWORD=admin123`).
2. Env-var pair that pre-seeds default username `admin` together
   with default password `admin123` on the same compose / env file
   (`CALIBRE_WEB_USER=admin` + `CALIBRE_WEB_PASSWORD=admin123`).
3. SQL bootstrap that inserts `('admin', 'admin123', ...)` into the
   `user` table (raw plaintext or trivially MD5/SHA1 of `admin123`).
4. JSON / YAML config keys `default_admin_password: admin123` (or
   `admin_password: admin123`) in a calibre-web context (file path
   contains `calibre`, OR the same file mentions `calibre-web`,
   `calibreweb`, or `app.db`).
"""

from __future__ import annotations

import os
import re
import sys
from typing import Iterable, List

# Env vars that pre-seed admin123 (any of several documented names).
# Case-sensitive: env-var-style identifiers are uppercase by
# convention, so this avoids matching YAML keys like
# `admin_password:` which belong to other detectors.
_ENV_ADMIN123 = re.compile(
    r'''(?m)^\s*(?:export\s+|-\s+)?'''
    r'''(?:CALIBRE_WEB_ADMIN_PASSWORD|CALIBRE_WEB_PASSWORD|'''
    r'''CALIBREWEB_ADMIN_PASSWORD|ADMIN_PASSWORD)'''
    r'''\s*[:=]\s*["']?admin123["']?\b'''
)

# Env: explicit admin user setting.
_ENV_ADMIN_USER = re.compile(
    r'''(?im)^\s*(?:export\s+|-\s+)?'''
    r'''(?:CALIBRE_WEB_USER|CALIBRE_WEB_USERNAME|'''
    r'''CALIBREWEB_ADMIN_USER|ADMIN_USERNAME|ADMIN_USER)'''
    r'''\s*[:=]\s*["']?admin["']?\s*$'''
)

# SQL: INSERT INTO user ... 'admin' ... 'admin123'
_SQL_INSERT_DEFAULT = re.compile(
    r'''(?is)insert\s+into\s+(?:`?user`?|`?users`?)\b[^;]*?'''
    r'''['"]admin['"][^;]*?['"]admin123['"][^;]*?;'''
)

# SQL: hashed admin123 (MD5 = 0192023a7bbd73250516f069df18b500,
# SHA1 = 7c4a8d09ca3762af61e59520943dc26494f8941b) paired with 'admin'
_SQL_INSERT_HASHED = re.compile(
    r'''(?is)insert\s+into\s+(?:`?user`?|`?users`?)\b[^;]*?'''
    r'''['"]admin['"][^;]*?'''
    r'''(?:0192023a7bbd73250516f069df18b500|'''
    r'''7c4a8d09ca3762af61e59520943dc26494f8941b)[^;]*?;'''
)

# JSON / YAML key with admin123 value.
_CFG_DEFAULT_ADMIN_PW = re.compile(
    r'''(?im)["']?(?:default_admin_password|admin_password)["']?'''
    r'''\s*[:=]\s*["']admin123["']'''
)

_COMMENT_LINE = re.compile(r"^\s*(?:#|;|--|//)")

# Markers that disambiguate generic configs from calibre-web ones.
_CW_CONTEXT = re.compile(
    r'''(?i)\b(?:calibre[-_ ]?web|calibreweb|janeczku|app\.db|'''
    r'''CALIBRE_DBPATH|/books)\b'''
)


def scan_text(text: str, path: str) -> List[str]:
    findings: List[str] = []

    # Whole-file SQL scan first (multi-line statements).
    for m in _SQL_INSERT_DEFAULT.finditer(text):
        lineno = text.count("\n", 0, m.start()) + 1
        snippet = m.group(0).replace("\n", " ")[:160]
        findings.append(
            f"{path}:{lineno}: SQL bootstrap inserts the default "
            f"calibre-web admin/admin123 into the user table "
            f"(CWE-798/CWE-1392): {snippet}"
        )
    for m in _SQL_INSERT_HASHED.finditer(text):
        lineno = text.count("\n", 0, m.start()) + 1
        snippet = m.group(0).replace("\n", " ")[:160]
        findings.append(
            f"{path}:{lineno}: SQL bootstrap inserts admin with the "
            f"known MD5/SHA1 hash of admin123 (CWE-798/CWE-521): "
            f"{snippet}"
        )

    has_admin_user = bool(_ENV_ADMIN_USER.search(text))
    has_cw_context = (
        bool(_CW_CONTEXT.search(text))
        or "calibre" in path.lower()
    )

    for lineno, raw in enumerate(text.splitlines(), start=1):
        if _COMMENT_LINE.match(raw):
            continue

        if _ENV_ADMIN123.search(raw):
            findings.append(
                f"{path}:{lineno}: env override pre-seeds the "
                f"calibre-web default admin password `admin123` "
                f"(CWE-798/CWE-1392): {raw.strip()[:160]}"
            )
            continue

        if _CFG_DEFAULT_ADMIN_PW.search(raw) and has_cw_context:
            findings.append(
                f"{path}:{lineno}: config sets "
                f"`admin_password: admin123` in a calibre-web context "
                f"(CWE-798/CWE-521): {raw.strip()[:160]}"
            )
            continue

        # ADMIN_USERNAME=admin alone is fine; only flag in a
        # calibre-web context when paired with admin123 elsewhere
        # in the same file (already caught above as _ENV_ADMIN123).
        # Keeping has_admin_user computed for future expansion.
        _ = has_admin_user

    return findings


_TARGET_NAMES = (
    "dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
)
_TARGET_EXTS = (
    ".json", ".yaml", ".yml", ".conf", ".ini", ".env", ".sh",
    ".bash", ".sql", ".service", ".tpl", ".example",
)


def iter_paths(roots: Iterable[str]) -> Iterable[str]:
    for r in roots:
        if os.path.isdir(r):
            for dp, _dn, fn in os.walk(r):
                for f in fn:
                    low = f.lower()
                    if low in _TARGET_NAMES or low.startswith("dockerfile"):
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
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                text = f.read()
        except OSError as e:
            sys.stderr.write(f"warn: cannot read {path}: {e}\n")
            continue
        for line in scan_text(text, path):
            print(line)
            any_finding = True
    return 1 if any_finding else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
