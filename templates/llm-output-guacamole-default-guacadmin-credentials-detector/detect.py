#!/usr/bin/env python3
"""
llm-output-guacamole-default-guacadmin-credentials-detector

Flags **Apache Guacamole** (the clientless remote-desktop gateway,
guacamole.apache.org / github.com/apache/guacamole-server +
guacamole-client) deployments where the default
`guacadmin` / `guacadmin` database credentials shipped in the
upstream `initdb.sql` are left in place, OR where the only
configured admin user has a weak / default password.

Why it matters
--------------
The Guacamole web client (`guacamole.war`) authenticates against
the JDBC auth backend by default. The official MySQL/PostgreSQL
init script (`guacamole-auth-jdbc-*.jar -> /schema/initdb.sql` or
`docker run guacamole/guacamole /opt/guacamole/bin/initdb.sh`)
creates a single bootstrap admin:

    username: guacadmin
    password: guacadmin
    (SHA-256 of "guacadmin" + per-row salt; the upstream literal
     hash CA458A7D494E3BE824F5E1E175A1556C0F8EEF2C2D7DF3633BEC4A29
     C4411960 appears verbatim in initdb.sql)

Anyone who reaches the Guacamole web port with these credentials
inherits SYSTEM_ADMINISTER permission, which means they can:

  * read every saved RDP/VNC/SSH connection (including stored
    passwords — Guacamole stores them in the JDBC schema and
    decrypts them on demand),
  * pivot into every host those connections target,
  * create new admin users and lock the operator out,
  * tail every active session via screen recording.

Maps to:
  - CWE-798: Use of Hard-coded Credentials
  - CWE-1392: Use of Default Credentials
  - CWE-521: Weak Password Requirements
  - CWE-1188: Insecure Default Initialization of Resource
  - OWASP A05:2021 Security Misconfiguration
  - OWASP A07:2021 Identification & Authentication Failures

Heuristic
---------
In `guac*`-named files, `*.env*`, `docker-compose.*`, `*.y*ml`,
`*.sql`, `*.conf`, `*.sh`, `Dockerfile*`, `*.toml`, `*.json`, and
any file whose body matches Guacamole scope hints
(`guacamole/guacamole`, `guacamole/guacd`, `guacamole-auth-jdbc`,
`/etc/guacamole`, `GUACAMOLE_HOME`, `guacd_hostname`,
`mysql-username`, when paired with `guacamole`), we flag:

1. Literal occurrence of the upstream initdb hash
   `CA458A7D494E3BE824F5E1E175A1556C0F8EEF2C2D7DF3633BEC4A29C4411960`
   (case-insensitive).
2. Any line that contains `guacadmin` AND a plaintext-credential
   shape (`PASSWORD`, `'guacadmin'`, `password=guacadmin`,
   `pass: guacadmin`, etc.) — i.e. operator left the bootstrap
   admin in place.
3. `guacamole-username` / `mysql-username` = `guacadmin` paired
   with `guacamole-password` / `mysql-password` = a weak literal
   (empty, `guacadmin`, `guacamole`, `password`, `changeme`,
   `secret`, `admin`, `root`, `test`, `demo`, `12345*`,
   `qwerty`, `letmein`, or any value < 12 chars).

We do NOT flag:

  * `${...}` / `{{ ... }}` template references for password
    fields.
  * Long high-entropy passwords not in the weak list.
  * `.md` / `.rst` / `.txt` / `.adoc` prose.
  * Files with no Guacamole scope hint.

Stdlib-only. Exit codes: 0 = clean, 1 = findings, 2 = usage error.
"""

from __future__ import annotations

import os
import re
import sys
from typing import Iterable, List

_GUAC_SCOPE_HINTS = (
    "guacamole/guacamole",
    "guacamole/guacd",
    "guacamole-auth-jdbc",
    "guacamole_home",
    "/etc/guacamole",
    "guacd_hostname",
    "guacd-hostname",
    "guacamole-username",
    "guacamole-password",
    "image: guacamole",
    "guacamole.properties",
    "initdb.sh",
    "/opt/guacamole",
)

_PROSE_EXTS = (".md", ".rst", ".txt", ".adoc")
_COMMENT_LINE = re.compile(r"^\s*[#;]")

# Upstream hash from guacamole-auth-jdbc initdb.sql for password "guacadmin".
_UPSTREAM_HASH = "CA458A7D494E3BE824F5E1E175A1556C0F8EEF2C2D7DF3633BEC4A29C4411960"

# Inline plaintext credential patterns mentioning guacadmin.
_GUACADMIN_PLAIN_RE = re.compile(
    r"""(?ix)
        (?:password|passwd|pass|pwd|admin_pass|admin_password|
            mysql[-_]password|guacamole[-_]password)
        \s*[:=]\s*
        ['"]?guacadmin['"]?
    """
)
# Or `'guacadmin', 'guacadmin'` style INSERT row.
_GUACADMIN_INSERT_RE = re.compile(
    r"""(?i)['"]guacadmin['"]\s*,\s*['"]guacadmin['"]"""
)

# Username/password key=value extractor for the third rule.
_KV_RE = re.compile(
    r"""(?ix)
        (?P<key>mysql[-_]username|mysql[-_]password
                |guacamole[-_]username|guacamole[-_]password
                |postgres[-_]username|postgres[-_]password)
        \s*[:=]\s*
        (?:"(?P<dval>[^"\n]*)"
          |'(?P<sval>[^'\n]*)'
          |(?P<bval>[^"'\s,}#\n]+))
    """
)

_WEAK_PASSES = {
    "",
    "guacadmin", "guacamole",
    "admin", "administrator",
    "password", "passwd", "pass", "pwd",
    "change_me", "changeme", "change-me", "changeit",
    "secret", "default", "test", "demo", "example",
    "12345", "123456", "1234567", "12345678", "123456789",
    "qwerty", "letmein", "root", "user",
    "p@ssw0rd", "password1",
}


def _is_template_ref(v: str) -> bool:
    return "${" in v or v.startswith("$") or "{{" in v


def _file_in_scope(text: str, path: str) -> bool:
    base = os.path.basename(path).lower()
    if "guacamole" in base or base.startswith("guac"):
        return True
    low = text.lower()
    return any(h in low for h in _GUAC_SCOPE_HINTS)


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

    # Username/password sweep -- track per-line MySQL/Guacamole creds.
    user_lines = {}  # lineno -> (key, val)
    pass_lines = {}

    for lineno, raw in enumerate(text.splitlines(), start=1):
        if _COMMENT_LINE.match(raw):
            continue
        line = raw.split("#", 1)[0]

        # Rule 1: upstream hash.
        if _UPSTREAM_HASH.lower() in line.lower():
            findings.append(
                f"{path}:{lineno}: guacamole upstream initdb hash "
                f"{_UPSTREAM_HASH} present -> bootstrap admin "
                f"`guacadmin` still has its default password "
                f"`guacadmin`; anyone reaching the web port becomes "
                f"SYSTEM_ADMINISTER and can read every stored "
                f"RDP/VNC/SSH credential (CWE-798/CWE-1392): "
                f"{raw.strip()[:160]}"
            )

        # Rule 2: inline plaintext guacadmin credentials.
        if _GUACADMIN_PLAIN_RE.search(line) or _GUACADMIN_INSERT_RE.search(line):
            findings.append(
                f"{path}:{lineno}: guacamole plaintext default "
                f"credentials `guacadmin` / `guacadmin` present -> "
                f"bootstrap admin left in place; any network-reachable "
                f"attacker becomes SYSTEM_ADMINISTER (CWE-798/"
                f"CWE-1392): {raw.strip()[:160]}"
            )

        # Rule 3: structured key/value collection.
        for m in _KV_RE.finditer(line):
            key = m.group("key").lower()
            val = (m.group("dval") or m.group("sval") or m.group("bval") or "")
            if "username" in key:
                user_lines[lineno] = (key, val)
            else:
                pass_lines[lineno] = (key, val)

    # Now flag weak passwords paired with a guacadmin username, OR
    # any guac-scoped weak DB password regardless of username.
    for lineno, (key, val) in pass_lines.items():
        v = val.strip().strip('"').strip("'")
        if _is_template_ref(v):
            continue
        if v.lower() in _WEAK_PASSES or len(v) < 12:
            kind = "weak literal" if v.lower() in _WEAK_PASSES else f"only {len(v)} chars"
            findings.append(
                f"{path}:{lineno}: guacamole {key} = {val!r} ({kind}) "
                f"-> Guacamole's JDBC backend stores every saved "
                f"RDP/VNC/SSH connection password; a weak DB or "
                f"admin password makes that vault trivially "
                f"reachable (CWE-521/CWE-798): {raw.strip()[:160]}"
            )

    # Dedupe while preserving order.
    seen = set()
    out = []
    for f in findings:
        if f not in seen:
            seen.add(f)
            out.append(f)
    return out


_TARGET_EXTS = (
    ".conf", ".yaml", ".yml", ".ini", ".env", ".env.example",
    ".env.sample", ".sh", ".bash", ".dockerfile", ".toml", ".json",
    ".sql", ".properties",
)


def iter_paths(roots: Iterable[str]) -> Iterable[str]:
    for r in roots:
        if os.path.isdir(r):
            for dp, _dn, fn in os.walk(r):
                for f in fn:
                    low = f.lower()
                    if (
                        "guac" in low
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
