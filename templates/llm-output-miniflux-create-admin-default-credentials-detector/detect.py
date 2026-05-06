#!/usr/bin/env python3
"""
llm-output-miniflux-create-admin-default-credentials-detector

Flags **Miniflux** (the minimalist self-hosted RSS reader,
miniflux.app / github.com/miniflux/v2) deployments where the
`CREATE_ADMIN=1` bootstrap flow is left at default / weak
credentials.

Why it matters
--------------
Miniflux supports a one-shot first-boot admin bootstrap controlled
by three env vars:

    CREATE_ADMIN=1
    ADMIN_USERNAME=admin
    ADMIN_PASSWORD=test123

(or `miniflux -create-admin` with the same env vars on the
command line). If `ADMIN_PASSWORD` is left at an obvious literal
or below the upstream-recommended length, anyone reaching the
Miniflux HTTP port can:

  * read every subscribed feed and every saved article (which
    often includes private OAuth-callback URLs, account-recovery
    emails the user starred, internal RSS feeds from Sentry /
    GitHub / Jira / Confluence, etc.),
  * use the integrated fetcher to make outbound HTTP requests on
    the operator's behalf — Miniflux follows redirects and will
    happily fetch from `http://169.254.169.254/...` (cloud
    metadata SSRF) unless `FETCHER_PROXY` / a deny-list is set,
  * mint API tokens that survive password changes,
  * create new admin users.

The official upstream docs and `docker-compose.yml` snippets in
the README use `ADMIN_USERNAME=admin` `ADMIN_PASSWORD=test123` as
the worked example, and many tutorials / blog posts copy them
verbatim. LLM completions reproduce the literals.

Maps to:
  - CWE-798: Use of Hard-coded Credentials
  - CWE-1392: Use of Default Credentials
  - CWE-521: Weak Password Requirements
  - CWE-1188: Insecure Default Initialization of Resource
  - OWASP A05:2021 Security Misconfiguration
  - OWASP A07:2021 Identification & Authentication Failures

Heuristic
---------
In `miniflux*`-named files, `*.env*`, `docker-compose.*`, `*.y*ml`,
`*.conf`, `*.sh`, `Dockerfile*`, `*.toml`, `*.json`, and any file
whose body matches Miniflux scope hints (`miniflux/miniflux`,
`miniflux:`, `MINIFLUX_`, `image: miniflux`, `/var/lib/miniflux`,
`run_migrations`, `database_url=postgres`, when paired with
`miniflux`), we flag:

1. `ADMIN_USERNAME=<weak>` -- empty, `admin`, `root`, `miniflux`,
   `user`, `default`, `test`, `demo`, `guest`.
2. `ADMIN_PASSWORD=<weak>` -- empty, `test123` (upstream literal),
   `admin`, `password`, `miniflux`, `changeme`, `secret`,
   `12345*`, `qwerty`, `letmein`, `root`, `p@ssw0rd`,
   `password1`, `default`, `test`, `demo`, or any value
   `< 12` chars.
3. `CREATE_ADMIN=1` AND no `ADMIN_PASSWORD` defined in the same
   file -- means the bootstrap will fall back to interactive /
   empty, or to a value baked into the container image.

We do NOT flag:

  * `${...}` / `{{ ... }}` template references for username /
    password fields.
  * Long high-entropy passwords not in the weak list.
  * `.md` / `.rst` / `.txt` / `.adoc` prose.
  * Files with no Miniflux scope hint.

Stdlib-only. Exit codes: 0 = clean, 1 = findings, 2 = usage error.
"""

from __future__ import annotations

import os
import re
import sys
from typing import Iterable, List

_MINIFLUX_SCOPE_HINTS = (
    "miniflux/miniflux",
    "miniflux:",
    "miniflux_",
    "image: miniflux",
    "/var/lib/miniflux",
    "/etc/miniflux.conf",
    "miniflux.conf",
    "run_migrations",
    "fetcher_proxy",
    "polling_frequency",
    "database_url=postgres",
)

_PROSE_EXTS = (".md", ".rst", ".txt", ".adoc")
_COMMENT_LINE = re.compile(r"^\s*[#;]")

_KV_RE = re.compile(
    r"""(?P<key>CREATE_ADMIN|ADMIN_USERNAME|ADMIN_PASSWORD)
        \s*[:=]\s*
        (?:"(?P<dval>[^"\n]*)"
          |'(?P<sval>[^'\n]*)'
          |(?P<bval>[^"'\s,}#\n]*))""",
    re.VERBOSE,
)

_WEAK_USERS = {
    "", "admin", "administrator", "root", "miniflux",
    "user", "users", "default", "test", "demo", "guest",
}

_WEAK_PASSES = {
    "",
    "test123", "test1234", "test12345",
    "admin", "administrator",
    "password", "passwd", "pass",
    "miniflux",
    "change_me", "changeme", "change-me", "changeit",
    "secret", "default", "test", "demo", "example",
    "12345", "123456", "1234567", "12345678", "123456789",
    "qwerty", "letmein", "root", "user",
    "p@ssw0rd", "password1",
}

_TRUE_TOKENS = {"1", "true", "yes", "on", "enabled"}


def _is_template_ref(v: str) -> bool:
    return "${" in v or v.startswith("$") or "{{" in v


def _file_in_scope(text: str, path: str) -> bool:
    base = os.path.basename(path).lower()
    if "miniflux" in base:
        return True
    low = text.lower()
    return any(h in low for h in _MINIFLUX_SCOPE_HINTS)


def scan(path: str) -> List[str]:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
    except OSError as e:
        sys.stderr.write(f"warn: cannot read {path}: {e}\n")
        return []
    base = os.path.basename(path).lower()
    if base.endswith(_PROSE_EXTS):
        return []
    if not _file_in_scope(text, path):
        return []

    findings: List[str] = []
    has_create = False
    has_password = False
    create_lineno = 0
    create_raw = ""

    for lineno, raw in enumerate(text.splitlines(), start=1):
        if _COMMENT_LINE.match(raw):
            continue
        line = raw.split("#", 1)[0]
        for m in _KV_RE.finditer(line):
            key = m.group("key")
            val = (m.group("dval") or m.group("sval") or m.group("bval") or "").strip()
            v_low = val.strip().strip('"').strip("'").lower()

            if key == "CREATE_ADMIN":
                if v_low in _TRUE_TOKENS:
                    has_create = True
                    create_lineno = lineno
                    create_raw = raw
            elif key == "ADMIN_USERNAME":
                if _is_template_ref(val):
                    continue
                if v_low in _WEAK_USERS:
                    findings.append(
                        f"{path}:{lineno}: miniflux ADMIN_USERNAME = "
                        f"{val!r} -> weak / default bootstrap admin "
                        f"username; combined with a weak password "
                        f"gives full UI + API access (CWE-1392): "
                        f"{raw.strip()[:160]}"
                    )
            elif key == "ADMIN_PASSWORD":
                has_password = True
                if _is_template_ref(val):
                    continue
                stripped = val.strip().strip('"').strip("'")
                if stripped.lower() in _WEAK_PASSES:
                    findings.append(
                        f"{path}:{lineno}: miniflux ADMIN_PASSWORD = "
                        f"{val!r} -> upstream-tutorial / weak literal; "
                        f"attacker can read every saved article and "
                        f"abuse the fetcher for SSRF (CWE-798/"
                        f"CWE-1392/CWE-521): {raw.strip()[:160]}"
                    )
                elif len(stripped) < 12:
                    findings.append(
                        f"{path}:{lineno}: miniflux ADMIN_PASSWORD is "
                        f"{len(stripped)} chars (< 12) -> too short "
                        f"for an admin password reachable over "
                        f"HTTP(S) (CWE-521): {raw.strip()[:160]}"
                    )

    if has_create and not has_password:
        findings.append(
            f"{path}:{create_lineno}: miniflux CREATE_ADMIN=1 set "
            f"but no ADMIN_PASSWORD defined in the same file -> "
            f"bootstrap will fail closed OR fall back to a literal "
            f"baked into the container / wrapper script; the admin "
            f"password is effectively undefined and almost certainly "
            f"weak in practice (CWE-1188/CWE-521): "
            f"{create_raw.strip()[:160]}"
        )
    return findings


_TARGET_EXTS = (
    ".conf", ".yaml", ".yml", ".ini", ".env", ".env.example",
    ".env.sample", ".sh", ".bash", ".dockerfile", ".toml", ".json",
)


def iter_paths(roots: Iterable[str]) -> Iterable[str]:
    for r in roots:
        if os.path.isdir(r):
            for dp, _dn, fn in os.walk(r):
                for f in fn:
                    low = f.lower()
                    if (
                        "miniflux" in low
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
