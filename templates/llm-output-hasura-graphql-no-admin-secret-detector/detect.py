#!/usr/bin/env python3
"""
llm-output-hasura-graphql-no-admin-secret-detector

Flags Hasura GraphQL Engine configurations that omit
HASURA_GRAPHQL_ADMIN_SECRET. Without it, the Hasura Console, the
metadata API, and `run_sql` (which is effectively superuser SQL on
the backing Postgres) are exposed unauthenticated.

Maps to CWE-306 / CWE-1188 / CWE-284.

Stdlib-only. Reads files passed on argv (recurses into dirs and picks
docker-compose.*, Dockerfile*, *.yaml, *.yml, *.env, *.sh, *.bash).

Exit codes: 0 = no findings, 1 = findings, 2 = usage error.
"""

from __future__ import annotations

import os
import re
import sys
from typing import Iterable, List, Tuple

_HASURA_IMAGE = re.compile(r"""hasura/graphql-engine\b""", re.IGNORECASE)
_ENABLE_CONSOLE_TRUE = re.compile(
    r"""HASURA_GRAPHQL_ENABLE_CONSOLE\s*[:=]\s*["']?(?:true|1|yes)["']?""",
    re.IGNORECASE,
)
_ADMIN_SECRET_KEY = re.compile(
    r"""HASURA_GRAPHQL_ADMIN_SECRET\b""",
)
# Empty / placeholder admin secret literal:
#   HASURA_GRAPHQL_ADMIN_SECRET=
#   HASURA_GRAPHQL_ADMIN_SECRET=""
#   HASURA_GRAPHQL_ADMIN_SECRET: ""
#   HASURA_GRAPHQL_ADMIN_SECRET: changeme
_EMPTY_OR_PLACEHOLDER = re.compile(
    r"""HASURA_GRAPHQL_ADMIN_SECRET\s*[:=]\s*"""
    r"""(?:["']?\s*["']?\s*$|["']?(?:changeme|change-me|placeholder|todo|secret|admin|password)["']?\s*$)""",
    re.IGNORECASE | re.MULTILINE,
)
# `docker run ... -e HASURA_GRAPHQL_ENABLE_CONSOLE=true` style on a single line
_DOCKER_RUN_HASURA = re.compile(
    r"""docker\s+run\b[^\n]*hasura/graphql-engine""",
    re.IGNORECASE,
)

_COMMENT_LINE = re.compile(r"""^\s*(?:#|//)""")


def _strip_inline_comment(line: str) -> str:
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


def _has_admin_secret_with_value(text: str) -> bool:
    """True iff some non-empty, non-placeholder admin secret is configured."""
    for raw in text.splitlines():
        if _COMMENT_LINE.match(raw):
            continue
        line = _strip_inline_comment(raw)
        if not _ADMIN_SECRET_KEY.search(line):
            continue
        # `valueFrom:` (k8s secretKeyRef) on the same or following lines
        # is detected at the file level below; here we look for inline literal.
        # Reject empty / placeholder.
        if _EMPTY_OR_PLACEHOLDER.search(line):
            continue
        # Look for `=<something non-empty>` or `: <something non-empty>`
        m = re.search(
            r"""HASURA_GRAPHQL_ADMIN_SECRET\s*[:=]\s*(.+?)\s*$""",
            line,
        )
        if m:
            val = m.group(1).strip().strip('"').strip("'")
            if val and val.lower() not in {
                "changeme", "change-me", "placeholder", "todo",
                "secret", "admin", "password", "",
            }:
                return True
        # YAML `valueFrom:` block referencing a secret resolves at file
        # scope; treat presence of `valueFrom` near the key as a value.
    # File-level: env entry name with valueFrom
    if re.search(
        r"""(?ms)name:\s*HASURA_GRAPHQL_ADMIN_SECRET\s*\n[^\n]*valueFrom\s*:""",
        text,
    ):
        return True
    return False


def scan_text(text: str, path: str) -> List[str]:
    findings: List[str] = []

    mentions_hasura = bool(_HASURA_IMAGE.search(text))
    has_enable_console = bool(_ENABLE_CONSOLE_TRUE.search(text))
    has_secret = _has_admin_secret_with_value(text)

    # Per-line: explicit empty / placeholder admin secret is always a finding.
    for lineno, raw in enumerate(text.splitlines(), start=1):
        if _COMMENT_LINE.match(raw):
            continue
        line = _strip_inline_comment(raw)
        if _EMPTY_OR_PLACEHOLDER.search(line):
            findings.append(
                f"{path}:{lineno}: HASURA_GRAPHQL_ADMIN_SECRET set to "
                f"empty / placeholder value (CWE-306/CWE-1188): "
                f"{raw.strip()[:160]}"
            )

    if not mentions_hasura:
        return findings

    if not has_secret:
        # File-level finding tied to first hasura image / enable-console line.
        for lineno, raw in enumerate(text.splitlines(), start=1):
            if _COMMENT_LINE.match(raw):
                continue
            line = _strip_inline_comment(raw)
            if _DOCKER_RUN_HASURA.search(line) and not _ADMIN_SECRET_KEY.search(text):
                findings.append(
                    f"{path}:{lineno}: `docker run hasura/graphql-engine` "
                    f"without HASURA_GRAPHQL_ADMIN_SECRET (CWE-306/CWE-284): "
                    f"{raw.strip()[:160]}"
                )
                return findings
        if has_enable_console:
            for lineno, raw in enumerate(text.splitlines(), start=1):
                if _COMMENT_LINE.match(raw):
                    continue
                line = _strip_inline_comment(raw)
                if _ENABLE_CONSOLE_TRUE.search(line):
                    findings.append(
                        f"{path}:{lineno}: hasura/graphql-engine with "
                        f"HASURA_GRAPHQL_ENABLE_CONSOLE=true and no "
                        f"HASURA_GRAPHQL_ADMIN_SECRET (CWE-306/CWE-1188): "
                        f"{raw.strip()[:160]}"
                    )
                    return findings
        # Otherwise still a finding: hasura image referenced with no secret.
        for lineno, raw in enumerate(text.splitlines(), start=1):
            if _COMMENT_LINE.match(raw):
                continue
            line = _strip_inline_comment(raw)
            if _HASURA_IMAGE.search(line):
                findings.append(
                    f"{path}:{lineno}: hasura/graphql-engine referenced "
                    f"with no HASURA_GRAPHQL_ADMIN_SECRET in file "
                    f"(CWE-306/CWE-284): {raw.strip()[:160]}"
                )
                return findings

    return findings


_TARGET_NAMES = (
    "dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
)
_TARGET_EXTS = (
    ".yaml", ".yml", ".env", ".sh", ".bash", ".tpl",
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
