#!/usr/bin/env python3
"""
llm-output-pgbouncer-auth-type-trust-detector

Flags PgBouncer configurations that set `auth_type = trust`. PgBouncer
is a connection pooler in front of PostgreSQL; with `trust`, it skips
all client password verification and just opens the upstream Postgres
connection using whatever password sits in `userlist.txt`. Anyone who
can reach the PgBouncer port can log in as any listed user.

Maps to:
- CWE-306: Missing Authentication for Critical Function.
- CWE-1188: Insecure Default Initialization of Resource.
- CWE-284: Improper Access Control.

Stdlib-only. Reads files passed on argv (recurses into dirs and picks
pgbouncer.ini, *.ini, *.conf, *.cnf, Dockerfile, docker-compose.*,
*.yaml, *.yml, *.sh, *.bash, *.service, *.env, Helm template files).

Exit codes: 0 = no findings, 1 = findings, 2 = usage error.

Heuristic
---------
We flag any of the following textual occurrences (outside `;` / `#`
comment lines):

1. `auth_type = trust` (or `auth_type=trust`, any spacing) in a
   pgbouncer.ini-style directive line.
2. `--auth_type=trust` or `--auth_type trust` on a pgbouncer command
   line (Dockerfile CMD/ENTRYPOINT, shell wrapper, systemd ExecStart,
   k8s args).
3. Exec-array form: ["pgbouncer", ..., "--auth_type", "trust"]
   (k8s container args / docker-compose command).
4. `PGBOUNCER_AUTH_TYPE=trust` env var (templated images).

Each occurrence emits one finding line.
"""

from __future__ import annotations

import os
import re
import sys
from typing import Iterable, List

# pgbouncer.ini directive: `auth_type = trust`
_INI_DIRECTIVE = re.compile(
    r"""(?im)^\s*auth_type\s*=\s*["']?trust["']?\s*(?:[;#].*)?$"""
)

# CLI flag: `--auth_type=trust` or `--auth_type trust`
_CLI_FLAG = re.compile(
    r"""--auth_type(?:\s+|=)["']?trust["']?\b"""
)

# Exec-array form: ["pgbouncer", ..., "--auth_type", "trust", ...]
_EXEC_ARRAY = re.compile(
    r"""\[[^\]]*["']pgbouncer["'][^\]]*"""
    r"""["']--auth_type["']\s*,\s*["']trust["'][^\]]*\]"""
)

# Env-var override used by edoburu/bitnami/etc. templated images.
_ENV_OVERRIDE = re.compile(
    r"""(?im)^\s*(?:export\s+)?PGBOUNCER_AUTH_TYPE\s*[:=]\s*["']?trust["']?\b"""
)

_COMMENT_LINE = re.compile(r"""^\s*[#;]""")


def _strip_inline_comment(line: str) -> str:
    """Strip trailing `#` / `;` comments outside quotes (best effort)."""
    out = []
    in_s = False
    in_d = False
    for ch in line:
        if ch == "'" and not in_d:
            in_s = not in_s
        elif ch == '"' and not in_s:
            in_d = not in_d
        elif ch in ("#", ";") and not in_s and not in_d:
            break
        out.append(ch)
    return "".join(out)


def scan_text(text: str, path: str) -> List[str]:
    findings: List[str] = []
    for lineno, raw in enumerate(text.splitlines(), start=1):
        if _COMMENT_LINE.match(raw):
            continue
        # The INI directive regex itself anchors on `^\s*auth_type` and
        # tolerates trailing comments, so check it before stripping.
        if _INI_DIRECTIVE.search(raw):
            findings.append(
                f"{path}:{lineno}: pgbouncer.ini directive `auth_type = trust` "
                f"disables PgBouncer client auth (CWE-306/CWE-1188): "
                f"{raw.strip()[:160]}"
            )
            continue

        line = _strip_inline_comment(raw)

        if _EXEC_ARRAY.search(line):
            findings.append(
                f"{path}:{lineno}: exec-array launches pgbouncer with "
                f"--auth_type trust (CWE-306/CWE-1188): "
                f"{raw.strip()[:160]}"
            )
            continue
        if _CLI_FLAG.search(line):
            findings.append(
                f"{path}:{lineno}: pgbouncer invoked with "
                f"--auth_type=trust (CWE-306/CWE-1188): "
                f"{raw.strip()[:160]}"
            )
            continue
        if _ENV_OVERRIDE.search(raw):
            findings.append(
                f"{path}:{lineno}: PGBOUNCER_AUTH_TYPE=trust env override "
                f"templates pgbouncer.ini with trust auth (CWE-306/CWE-284): "
                f"{raw.strip()[:160]}"
            )
            continue
    return findings


_TARGET_NAMES = (
    "dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
    "pgbouncer.ini",
)
_TARGET_EXTS = (
    ".ini", ".conf", ".cnf", ".yaml", ".yml", ".sh", ".bash",
    ".service", ".tpl", ".env",
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
