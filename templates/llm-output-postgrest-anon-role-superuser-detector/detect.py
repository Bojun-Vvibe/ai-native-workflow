#!/usr/bin/env python3
"""
llm-output-postgrest-anon-role-superuser-detector

Flags PostgREST configurations whose `db-anon-role` (i.e. the Postgres
role used for unauthenticated HTTP requests) is the database superuser
or any equivalently broad role. Also flags SQL that grants superuser
/ bypassrls / blanket schema privileges to a role that another file
in the same tree wires up as `db-anon-role`.

Maps to CWE-269 / CWE-732 / CWE-284.

Stdlib-only. Reads files passed on argv (recurses into dirs and picks
*.conf, *.env, *.sh, *.bash, *.yaml, *.yml, *.sql, Dockerfile*,
docker-compose.*).

Exit codes: 0 = no findings, 1 = findings, 2 = usage error.
"""

from __future__ import annotations

import os
import re
import sys
from typing import Iterable, List

# Roles that are unambiguously dangerous as the anon role.
_FORBIDDEN_ROLES = {
    "postgres", "postgrest", "admin", "root", "dba", "superuser",
    "rds_superuser", "cloudsqlsuperuser",
}
_FORBIDDEN_ALT = "|".join(sorted(_FORBIDDEN_ROLES))

# postgrest.conf style: db-anon-role = "postgres" | db-anon-role = postgres
_CONF_DIRECTIVE = re.compile(
    r"""(?im)^\s*db-anon-role\s*=\s*["']?(""" + _FORBIDDEN_ALT + r""")["']?\s*$"""
)

# Env var: PGRST_DB_ANON_ROLE=postgres (also yaml `PGRST_DB_ANON_ROLE: postgres`)
_ENV_VAR = re.compile(
    r"""(?im)\bPGRST_DB_ANON_ROLE\s*[:=]\s*["']?(""" + _FORBIDDEN_ALT + r""")["']?\b"""
)

# CLI flag: postgrest --db-anon-role postgres
_CLI_FLAG = re.compile(
    r"""(?i)\bpostgrest\b[^\n]*--db-anon-role(?:\s+|=)["']?(""" + _FORBIDDEN_ALT + r""")["']?\b"""
)

# SQL: ALTER ROLE <name> SUPERUSER  /  ALTER ROLE <name> BYPASSRLS
_SQL_ALTER_SUPERUSER = re.compile(
    r"""(?i)\bALTER\s+ROLE\s+(["']?[A-Za-z_][A-Za-z0-9_]*["']?)\s+(?:WITH\s+)?(SUPERUSER|BYPASSRLS)\b"""
)
# SQL: CREATE ROLE foo SUPERUSER ... LOGIN
_SQL_CREATE_SUPERUSER = re.compile(
    r"""(?i)\bCREATE\s+ROLE\s+(["']?[A-Za-z_][A-Za-z0-9_]*["']?)\s+[^;]*\bSUPERUSER\b"""
)
# SQL: GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO foo
_SQL_GRANT_ALL = re.compile(
    r"""(?i)\bGRANT\s+ALL(?:\s+PRIVILEGES)?\s+ON\s+ALL\s+TABLES\s+IN\s+SCHEMA\s+\w+\s+TO\s+(["']?[A-Za-z_][A-Za-z0-9_]*["']?)\b"""
)

_LINE_COMMENT = re.compile(r"""^\s*(?:--|#|//)""")


def _strip_inline_sql_comment(line: str) -> str:
    # Strip `--` line comments and `#` line comments outside quotes.
    out = []
    in_s = False
    in_d = False
    i = 0
    while i < len(line):
        ch = line[i]
        nxt = line[i + 1] if i + 1 < len(line) else ""
        if ch == "'" and not in_d:
            in_s = not in_s
        elif ch == '"' and not in_s:
            in_d = not in_d
        elif not in_s and not in_d and ch == "-" and nxt == "-":
            # SQL `--` line comment requires whitespace or EOL after.
            after = line[i + 2] if i + 2 < len(line) else ""
            if after == "" or after.isspace():
                break
        elif not in_s and not in_d and ch == "#":
            break
        out.append(ch)
        i += 1
    return "".join(out)


def _collect_anon_role_names(text: str) -> set:
    """Extract every role name configured as the PostgREST anon role
    in this file (including the safe-looking ones), so we can flag
    SQL that grants those names superuser/bypassrls.
    """
    names = set()
    for m in re.finditer(
        r"""(?im)^\s*db-anon-role\s*=\s*["']?([A-Za-z_][A-Za-z0-9_]*)["']?""",
        text,
    ):
        names.add(m.group(1).lower())
    for m in re.finditer(
        r"""(?im)\bPGRST_DB_ANON_ROLE\s*[:=]\s*["']?([A-Za-z_][A-Za-z0-9_]*)["']?""",
        text,
    ):
        names.add(m.group(1).lower())
    for m in re.finditer(
        r"""(?i)\bpostgrest\b[^\n]*--db-anon-role(?:\s+|=)["']?([A-Za-z_][A-Za-z0-9_]*)["']?""",
        text,
    ):
        names.add(m.group(1).lower())
    return names


def scan_text(text: str, path: str) -> List[str]:
    findings: List[str] = []
    anon_names_in_file = _collect_anon_role_names(text)

    for lineno, raw in enumerate(text.splitlines(), start=1):
        if _LINE_COMMENT.match(raw):
            continue
        line = _strip_inline_sql_comment(raw)

        m = _CONF_DIRECTIVE.search(line)
        if m:
            findings.append(
                f"{path}:{lineno}: PostgREST db-anon-role set to "
                f"`{m.group(1)}` — anonymous HTTP requests run as a "
                f"superuser-class role (CWE-269/CWE-732): "
                f"{raw.strip()[:160]}"
            )
            continue

        m = _ENV_VAR.search(line)
        if m:
            findings.append(
                f"{path}:{lineno}: PGRST_DB_ANON_ROLE={m.group(1)} — "
                f"anonymous HTTP requests run as a superuser-class role "
                f"(CWE-269/CWE-732): {raw.strip()[:160]}"
            )
            continue

        m = _CLI_FLAG.search(line)
        if m:
            findings.append(
                f"{path}:{lineno}: postgrest invoked with "
                f"--db-anon-role {m.group(1)} (CWE-269/CWE-284): "
                f"{raw.strip()[:160]}"
            )
            continue

        m = _SQL_ALTER_SUPERUSER.search(line)
        if m:
            role = m.group(1).strip('"').strip("'").lower()
            attr = m.group(2).upper()
            if role in anon_names_in_file or role in _FORBIDDEN_ROLES:
                findings.append(
                    f"{path}:{lineno}: SQL grants {attr} to `{role}`, "
                    f"which is wired up as PostgREST anon role "
                    f"(CWE-269/CWE-732): {raw.strip()[:160]}"
                )
                continue

        m = _SQL_CREATE_SUPERUSER.search(line)
        if m:
            role = m.group(1).strip('"').strip("'").lower()
            if role in anon_names_in_file or role in _FORBIDDEN_ROLES:
                findings.append(
                    f"{path}:{lineno}: SQL CREATE ROLE `{role}` SUPERUSER "
                    f"and that role is the PostgREST anon role "
                    f"(CWE-269/CWE-732): {raw.strip()[:160]}"
                )
                continue

        m = _SQL_GRANT_ALL.search(line)
        if m:
            role = m.group(1).strip('"').strip("'").lower()
            if role in anon_names_in_file:
                findings.append(
                    f"{path}:{lineno}: SQL GRANT ALL PRIVILEGES ... TO "
                    f"`{role}` — that role is the PostgREST anon role "
                    f"(CWE-732/CWE-284): {raw.strip()[:160]}"
                )
                continue

    return findings


_TARGET_NAMES = (
    "dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
    "postgrest.conf",
)
_TARGET_EXTS = (
    ".conf", ".env", ".sh", ".bash", ".yaml", ".yml", ".sql", ".tpl",
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
