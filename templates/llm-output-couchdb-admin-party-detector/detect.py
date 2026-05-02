#!/usr/bin/env python3
"""
llm-output-couchdb-admin-party-detector

Flags Apache CouchDB configurations that leave the database in
**"Admin Party" mode** -- i.e. there are no admin credentials, so
**every anonymous HTTP client is implicitly an admin** and can:

  * create, drop, and replicate any database,
  * read and write any document,
  * change cluster-wide config (the `_node/_config` endpoint),
  * stand up replication jobs that exfiltrate to attacker-controlled
    targets.

CouchDB has been internet-scanned for exactly this misconfiguration
since 2017 (CVE-2017-12635 / CVE-2017-12636 amplified the impact, but
the open-by-default admin-party mode is the underlying issue). The
CouchDB docs are explicit:

> "CouchDB starts up in 'admin party' mode. This means anyone with
>  HTTP access can do anything, including delete databases. This is
>  not safe for production."
>  -- https://docs.couchdb.org/en/stable/setup/single-node.html

Maps to:
  - CWE-306: Missing Authentication for Critical Function
  - CWE-1188: Insecure Default Initialization of Resource
  - CWE-732: Incorrect Permission Assignment for Critical Resource
  - OWASP A05:2021 Security Misconfiguration

Why LLMs ship this
------------------
Quickstart docs and Docker examples often show `docker run -p 5984
couchdb` with no `COUCHDB_USER` / `COUCHDB_PASSWORD`. Models copy
that into "production" compose / k8s / Helm manifests.

Heuristic
---------
Three concrete forms:

1. **CouchDB ini config** (``local.ini``, ``default.ini``,
   ``*.ini``):

     [admins]
     ; (empty section -- admin party)

   or

     [admins]
     admin = admin            # plaintext default cred

   or the `[chttpd]` block opening to the world while no
   `[admins]` block is present (we can only detect the explicit
   empty / default-cred forms reliably).

2. **Docker / compose / k8s env**: the official `couchdb` image
   *requires* `COUCHDB_USER` and `COUCHDB_PASSWORD` -- if the env
   uses `COUCHDB_PASSWORD=password` / `admin` / `couchdb` etc. (well-
   known weak defaults), or hard-codes a password directly, we flag
   it. We also flag `--env COUCHDB_PASSWORD=` with empty value.

3. **CLI / shell**: `curl ... :5984/_users` style commands that pass
   no auth header are NOT flagged here (too noisy); we only flag the
   *server-side* config forms above.

Stdlib-only. Walks dirs, scans `*.ini`, `*.yaml`, `*.yml`, `*.env`,
`*.sh`, `*.bash`, `*.service`, `Dockerfile*`, `docker-compose.*`.

Exit codes: 0 = clean, 1 = findings, 2 = usage error.
"""

from __future__ import annotations

import os
import re
import sys
from typing import Iterable, List

_COMMENT_LINE = re.compile(r"""^\s*[#;]""")

# --- INI ---
_INI_ADMINS_HEADER = re.compile(
    r"""^\s*\[\s*admins\s*\]\s*(?:[#;].*)?$""", re.IGNORECASE,
)
_INI_ANY_HEADER = re.compile(r"""^\s*\[\s*[A-Za-z0-9_.\-]+\s*\]""")
# A real admin row looks like `name = secret`; we WANT to see at
# least one such row. We flag empty admins blocks AND well-known
# weak defaults.
_INI_KV = re.compile(
    r"""^\s*([A-Za-z0-9_.\-]+)\s*=\s*(.+?)\s*(?:[;#].*)?$""",
)
_WEAK_PASSWORDS = {
    "admin", "password", "couchdb", "changeme", "changeme!",
    "root", "12345", "123456", "letmein", "secret", "test",
    "default", "couch",
}

# --- ENV / shell / compose / Dockerfile ---
# COUCHDB_PASSWORD=<weak> (with optional surrounding quotes).
_ENV_PASS = re.compile(
    r"""\bCOUCHDB_PASSWORD\s*[=:]\s*["']?([^"'#\s]*)["']?""",
)
# COUCHDB_USER=<weak> (we report only when paired with weak pass).
# Hard-coded plaintext patterns we can flag stand-alone too:
#   ENV COUCHDB_PASSWORD password
_DOCKER_ENV_PASS = re.compile(
    r"""^\s*ENV\s+COUCHDB_PASSWORD\s+(?:["']?)([^"'\s]*)(?:["']?)\s*$""",
    re.IGNORECASE,
)


def _strip_shell_comment(line: str) -> str:
    out = []
    in_s = False
    in_d = False
    for ch in line:
        if ch == "'" and not in_d:
            in_s = not in_s
        elif ch == '"' and not in_s:
            in_d = not in_d
        elif ch == "#" and not in_s and not in_d:
            break
        out.append(ch)
    return "".join(out)


def _is_weak(pw: str) -> bool:
    if pw == "":
        return True
    if pw.lower() in _WEAK_PASSWORDS:
        return True
    return False


def scan_ini(text: str, path: str) -> List[str]:
    findings: List[str] = []
    lines = text.splitlines()
    in_admins = False
    admins_line = 0
    admin_rows: List[tuple] = []  # (lineno, name, value)
    flushed = False

    def _flush(end_line: int) -> None:
        nonlocal admin_rows, in_admins, flushed
        if not in_admins or flushed:
            return
        flushed = True
        if not admin_rows:
            findings.append(
                f"{path}:{admins_line}: couchdb [admins] section "
                f"empty -> Admin Party mode, anonymous HTTP = admin "
                f"(CWE-306/CWE-1188)"
            )
        else:
            for lineno, name, value in admin_rows:
                # Plaintext password (not a hashed `-pbkdf2-...`
                # / `-hashed-...` form).
                if value.startswith("-pbkdf2-") \
                        or value.startswith("-hashed-"):
                    continue
                if _is_weak(value):
                    findings.append(
                        f"{path}:{lineno}: couchdb [admins] "
                        f"{name}=<weak/default> plaintext credential "
                        f"(CWE-1188/CWE-732): {name} = {value[:40]}"
                    )

    for i, raw in enumerate(lines, start=1):
        if _INI_ADMINS_HEADER.match(raw):
            _flush(i)
            in_admins = True
            admins_line = i
            admin_rows = []
            flushed = False
            continue
        if in_admins:
            if _INI_ANY_HEADER.match(raw):
                _flush(i)
                in_admins = False
                continue
            if _COMMENT_LINE.match(raw) or raw.strip() == "":
                continue
            m = _INI_KV.match(raw)
            if m:
                admin_rows.append((i, m.group(1), m.group(2)))
    _flush(len(lines) + 1)
    return findings


def scan_env_like(text: str, path: str) -> List[str]:
    findings: List[str] = []
    for lineno, raw in enumerate(text.splitlines(), start=1):
        if _COMMENT_LINE.match(raw):
            continue
        line = _strip_shell_comment(raw)
        m = _DOCKER_ENV_PASS.match(line)
        if m:
            pw = m.group(1)
            if _is_weak(pw):
                findings.append(
                    f"{path}:{lineno}: COUCHDB_PASSWORD={pw or '<empty>'} "
                    f"in Dockerfile ENV -> weak/default admin "
                    f"credential (CWE-1188/CWE-798): {raw.strip()[:160]}"
                )
            continue
        for em in _ENV_PASS.finditer(line):
            pw = em.group(1)
            if _is_weak(pw):
                findings.append(
                    f"{path}:{lineno}: COUCHDB_PASSWORD={pw or '<empty>'} "
                    f"is a default/weak admin credential -> Admin "
                    f"Party with known password (CWE-1188/CWE-798): "
                    f"{raw.strip()[:160]}"
                )
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
    if low.endswith(".ini"):
        out.extend(scan_ini(text, path))
    if low.endswith((".yaml", ".yml", ".env", ".sh", ".bash",
                     ".service")):
        out.extend(scan_env_like(text, path))
    base = os.path.basename(low)
    if base.startswith("dockerfile") or base.startswith("docker-compose") \
            or low.endswith(".dockerfile"):
        out.extend(scan_env_like(text, path))
    return out


_TARGET_NAMES = ("dockerfile", "docker-compose.yml", "docker-compose.yaml")
_TARGET_EXTS = (".ini", ".yaml", ".yml", ".env",
                ".sh", ".bash", ".service", ".dockerfile")


def iter_paths(roots: Iterable[str]) -> Iterable[str]:
    for r in roots:
        if os.path.isdir(r):
            for dp, _dn, fn in os.walk(r):
                for f in fn:
                    low = f.lower()
                    if low in _TARGET_NAMES \
                            or low.startswith("dockerfile") \
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
