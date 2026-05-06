#!/usr/bin/env python3
"""
llm-output-umami-app-secret-default-detector

Flags **Umami** (privacy-focused web analytics) deployments where
`APP_SECRET` (the JWT signing key for admin sessions and API
tokens) is left at an empty string, an obvious placeholder, or a
short low-entropy value.

Umami uses `APP_SECRET` to sign:

  * the admin login JWT cookie
  * API tokens minted via `/api/auth/login` and the share-link API
  * password-reset tokens

Anyone who knows `APP_SECRET` can forge an admin JWT for any user
ID — they don't need the password, the database, or even network
access to the Umami host. They mint a cookie offline, paste it
into a browser, and they're root in the analytics tenant: they can
exfiltrate every site's pageview data, reset passwords, and pivot
to whatever upstream the dashboard is embedded in.

Maps to:
  - CWE-798: Use of Hard-coded Credentials
  - CWE-1392: Use of Default Credentials
  - CWE-330: Use of Insufficiently Random Values
  - CWE-521: Weak Password Requirements
  - CWE-1188: Insecure Default Initialization of Resource
  - OWASP A02:2021 Cryptographic Failures
  - OWASP A05:2021 Security Misconfiguration
  - OWASP A07:2021 Identification & Authentication Failures

Heuristic
---------
We flag, in `docker-compose.*`, `*.yml`, `*.yaml`, `*.env.example`,
`*.ini`, `*.conf`, `*.sh`, `Dockerfile*`, `*.toml`, `*.json`, and
any file whose basename contains `umami`:

1. `APP_SECRET` set to an empty string.
2. `APP_SECRET` set to a value in the placeholder set: `umami`,
   `secret`, `secretkey`, `secret-key`, `changeme`, `change-me`,
   `replace-me`, `your-secret-here`, `your_secret_here`,
   `your-app-secret`, `replaceme`, `default`, `password`, `admin`,
   `test`, `demo`, `12345*`.
3. `APP_SECRET` shorter than 32 characters.
4. `HASH_SALT` (legacy umami env var) with the same checks.

We do NOT flag:

  * `${...}` / `{{ ... }}` template references.
  * Long high-entropy values (>= 32 chars).
  * Doc / README mentions in prose.
  * Files with no umami scope hint.

Stdlib-only. Exit codes: 0 = clean, 1 = findings, 2 = usage error.
"""

from __future__ import annotations

import os
import re
import sys
from typing import Iterable, List

_UMAMI_SCOPE_HINTS = (
    "umami",
    "umamisoftware/umami",
    "ghcr.io/umami-software/umami",
)

_SECRET_KEY = re.compile(
    r"""(?P<key>APP_SECRET|HASH_SALT)\s*[:=]\s*
        (?:"(?P<dval>[^"\n]*)"
          |'(?P<sval>[^'\n]*)'
          |(?P<bval>[^"'\s,}#\n]*))""",
    re.VERBOSE,
)

_WEAK_SECRETS = {
    "",
    "umami", "umami-secret", "umami_secret",
    "secret", "secretkey", "secret-key", "secret_key",
    "changeme", "change-me", "changeit", "replaceme", "replace-me",
    "your-secret-here", "your_secret_here", "your-app-secret",
    "your_app_secret", "yoursecret", "your_secret",
    "default", "password", "passwd", "admin", "root",
    "test", "demo", "example", "placeholder",
    "12345", "123456", "1234567", "12345678",
    "qwerty", "letmein",
}

_COMMENT_LINE = re.compile(r"""^\s*[#;]""")


def _is_template_ref(v: str) -> bool:
    return "${" in v or v.startswith("$") or "{{" in v


def _file_in_scope(text: str, path: str) -> bool:
    base = os.path.basename(path).lower()
    if "umami" in base:
        return True
    low = text.lower()
    return any(h in low for h in _UMAMI_SCOPE_HINTS)


def _classify(val: str) -> str:
    v = val.strip().strip('"').strip("'")
    if _is_template_ref(v):
        return "ok"
    if v.lower() in _WEAK_SECRETS:
        return "weak"
    if len(v) < 32:
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
    if base.endswith((".md", ".rst", ".txt", ".adoc")):
        return []

    findings: List[str] = []
    for lineno, raw in enumerate(text.splitlines(), start=1):
        if _COMMENT_LINE.match(raw):
            continue
        line = raw.split("#", 1)[0]
        for m in _SECRET_KEY.finditer(line):
            key = m.group("key")
            val = m.group("dval") or m.group("sval") or m.group("bval") or ""
            kind = _classify(val)
            if kind == "weak":
                findings.append(
                    f"{path}:{lineno}: umami {key} = placeholder "
                    f"{val!r} -> attacker can forge an admin JWT "
                    f"offline and bypass login entirely "
                    f"(CWE-798/CWE-1392/CWE-330): {raw.strip()[:160]}"
                )
            elif kind == "short":
                findings.append(
                    f"{path}:{lineno}: umami {key} is {len(val.strip())} "
                    f"chars (< 32) -> insufficient entropy to resist "
                    f"offline JWT-key brute force (CWE-330/CWE-521): "
                    f"{raw.strip()[:160]}"
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
                        "umami" in low
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
