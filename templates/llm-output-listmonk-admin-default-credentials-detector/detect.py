#!/usr/bin/env python3
"""
llm-output-listmonk-admin-default-credentials-detector

Flags **listmonk** (newsletter / mailing-list manager) deployments
where the bootstrap superadmin is left at the well-known quickstart
values from the official docker-compose.

listmonk reads two env vars at first boot to seed the superadmin
account:

    LISTMONK_ADMIN_USER
    LISTMONK_ADMIN_PASSWORD

The official `docker-compose.yml` in the project README ships with:

    LISTMONK_ADMIN_USER=listmonk
    LISTMONK_ADMIN_PASSWORD=listmonk

Anyone with these credentials can log into `/admin/`, mint API
tokens, upload arbitrary subscriber lists, and — most importantly —
SEND mail through the configured upstream SMTP relay. That makes a
default-credentialed listmonk an instant open relay attached to a
real, warmed-up sender domain.

Maps to:
  - CWE-798: Use of Hard-coded Credentials
  - CWE-1392: Use of Default Credentials
  - CWE-521: Weak Password Requirements
  - CWE-1188: Insecure Default Initialization of Resource
  - OWASP A05:2021 Security Misconfiguration
  - OWASP A07:2021 Identification & Authentication Failures

Heuristic
---------
We flag, in `docker-compose.*`, `*.yml`, `*.yaml`, `*.env.example`,
`*.ini`, `*.conf`, `*.sh`, `Dockerfile*`, and any file whose
basename contains `listmonk`:

1. `LISTMONK_ADMIN_USER` set to one of: `listmonk`, `admin`, `root`,
   `user`, empty.
2. `LISTMONK_ADMIN_PASSWORD` set to one of: `listmonk`, `admin`,
   `password`, `changeme`, `change-me`, `default`, `12345*`,
   `qwerty`, `letmein`, empty, or any value < 12 chars.
3. The same key set to a value identical to its key (`listmonk` /
   `listmonk`) — the strongest signal of a copy-pasted quickstart.

We do NOT flag:

  * `${...}` / `{{ ... }}` template references (assume injected
    from a secret store at runtime).
  * Long high-entropy values (>= 12 chars, mixed character classes).
  * Doc / README mentions in prose.

Stdlib-only. Exit codes: 0 = clean, 1 = findings, 2 = usage error.
"""

from __future__ import annotations

import os
import re
import sys
from typing import Iterable, List

_LISTMONK_SCOPE_HINTS = (
    "listmonk",
    "listmonk/listmonk",
    "knadh/listmonk",
)

_USER_KEY = re.compile(
    r"""(?P<key>LISTMONK_ADMIN_USER)\s*[:=]\s*
        (?:"(?P<dval>[^"\n]*)"
          |'(?P<sval>[^'\n]*)'
          |(?P<bval>[^"'\s,}#\n]*))""",
    re.VERBOSE,
)

_PASS_KEY = re.compile(
    r"""(?P<key>LISTMONK_ADMIN_PASSWORD)\s*[:=]\s*
        (?:"(?P<dval>[^"\n]*)"
          |'(?P<sval>[^'\n]*)'
          |(?P<bval>[^"'\s,}#\n]*))""",
    re.VERBOSE,
)

_WEAK_USERS = {"", "listmonk", "admin", "root", "user", "test", "demo"}

_WEAK_PASSES = {
    "", "listmonk", "admin", "root", "password", "passwd", "pass",
    "changeme", "change-me", "changeit", "default", "test", "demo",
    "12345", "123456", "1234567", "12345678", "123456789",
    "qwerty", "letmein", "guest",
}

_COMMENT_LINE = re.compile(r"""^\s*[#;]""")


def _is_template_ref(v: str) -> bool:
    return "${" in v or v.startswith("$") or "{{" in v


def _file_in_scope(text: str, path: str) -> bool:
    base = os.path.basename(path).lower()
    if "listmonk" in base:
        return True
    low = text.lower()
    return any(h in low for h in _LISTMONK_SCOPE_HINTS)


def _classify_user(val: str) -> str:
    v = val.strip().strip('"').strip("'")
    if _is_template_ref(v):
        return "ok"
    if v.lower() in _WEAK_USERS:
        return "weak"
    return "ok"


def _classify_pass(val: str) -> str:
    v = val.strip().strip('"').strip("'")
    if _is_template_ref(v):
        return "ok"
    if v.lower() in _WEAK_PASSES:
        return "weak"
    if len(v) < 12:
        return "short"
    return "ok"


def scan(path: str) -> List[str]:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
    except OSError as e:
        sys.stderr.write(f"warn: cannot read {path}: {e}\n")
        return []
    if not _file_in_scope(text, path):
        return []
    base = os.path.basename(path).lower()
    # Skip prose / docs even if they mention listmonk in scope hints.
    if base.endswith((".md", ".rst", ".txt", ".adoc")):
        return []

    findings: List[str] = []
    for lineno, raw in enumerate(text.splitlines(), start=1):
        if _COMMENT_LINE.match(raw):
            continue
        line = raw.split("#", 1)[0]
        for m in _USER_KEY.finditer(line):
            val = m.group("dval") or m.group("sval") or m.group("bval") or ""
            kind = _classify_user(val)
            if kind == "weak":
                findings.append(
                    f"{path}:{lineno}: listmonk LISTMONK_ADMIN_USER = "
                    f"placeholder {val!r} -> well-known bootstrap "
                    f"superadmin account name (CWE-1392): "
                    f"{raw.strip()[:160]}"
                )
        for m in _PASS_KEY.finditer(line):
            val = m.group("dval") or m.group("sval") or m.group("bval") or ""
            kind = _classify_pass(val)
            if kind == "weak":
                findings.append(
                    f"{path}:{lineno}: listmonk LISTMONK_ADMIN_PASSWORD "
                    f"= placeholder {val!r} -> superadmin auth is "
                    f"effectively off; attacker can mint API tokens and "
                    f"send mail via the configured SMTP relay "
                    f"(CWE-798/CWE-1392): {raw.strip()[:160]}"
                )
            elif kind == "short":
                findings.append(
                    f"{path}:{lineno}: listmonk LISTMONK_ADMIN_PASSWORD "
                    f"is {len(val.strip())} chars (< 12) -> trivially "
                    f"brute-forced (CWE-521): {raw.strip()[:160]}"
                )
    return findings


_TARGET_EXTS = (
    ".conf", ".yaml", ".yml", ".ini", ".env.example",
    ".sh", ".bash", ".dockerfile", ".toml", ".json",
)


def iter_paths(roots: Iterable[str]) -> Iterable[str]:
    for r in roots:
        if os.path.isdir(r):
            for dp, _dn, fn in os.walk(r):
                for f in fn:
                    low = f.lower()
                    if (
                        "listmonk" in low
                        or low.startswith("dockerfile")
                        or low.startswith("docker-compose")
                        or low.endswith(_TARGET_EXTS)
                    ):
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
