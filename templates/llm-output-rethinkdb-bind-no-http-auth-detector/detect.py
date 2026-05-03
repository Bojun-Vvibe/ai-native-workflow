#!/usr/bin/env python3
"""
llm-output-rethinkdb-bind-no-http-auth-detector

Flags RethinkDB configurations / invocations that bind to all
interfaces without setting an initial admin password — leaving the
HTTP admin UI on :8080 reachable with the empty default password.

Maps to:
- CWE-306: Missing Authentication for Critical Function.
- CWE-1188: Insecure Default Initialization of Resource.
- CWE-668: Exposure of Resource to Wrong Sphere.

Stdlib-only. Reads files passed on argv (recurses into dirs and picks
Dockerfile, docker-compose.*, *.yaml, *.yml, *.sh, *.bash, *.service,
*.env, *.tpl, *.conf).

Exit codes: 0 = no findings, 1 = findings, 2 = usage error.
"""

from __future__ import annotations

import os
import re
import sys
from typing import Iterable, List, Tuple

# --bind all  /  --bind=all
_CLI_BIND_ALL = re.compile(
    r"""--bind(?:[=\s]+)['"]?all['"]?\b""",
    re.IGNORECASE,
)
# Bare flag (list-form: value on next list item)
_CLI_BIND_BARE = re.compile(r"""--bind\b""")

# rethinkdb.conf:  bind=all  (or bind = all, or bind: all)
_CONF_BIND_ALL = re.compile(
    r"""^\s*bind\s*[:=]\s*['"]?all['"]?\s*$""",
    re.IGNORECASE,
)

# initial-password: empty value forms
_CLI_PASSWORD_EMPTY = re.compile(
    r"""--initial-password(?:[=\s]+)?(?:['"]['"]|['"]?\s*$)""",
    re.IGNORECASE | re.MULTILINE,
)
_CONF_PASSWORD_EMPTY = re.compile(
    r"""^\s*initial-password\s*[:=]\s*(?:['"]['"]?|)\s*$""",
    re.IGNORECASE | re.MULTILINE,
)

# initial-password set to a non-empty value (anywhere in file)
_PASSWORD_SET = re.compile(
    r"""(?:--initial-password[=\s]+|^\s*initial-password\s*[:=]\s*)['"]?([^\s'"#]{1,})['"]?""",
    re.IGNORECASE | re.MULTILINE,
)

_COMMENT_LINE = re.compile(r"""^\s*[#;]""")

_RETHINK_CTX = re.compile(
    r"""(?i)\brethinkdb?\b|image:\s*['"]?rethinkdb"""
)


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


def _rethink_context(text: str) -> bool:
    return bool(_RETHINK_CTX.search(text))


def _has_password_set(text: str) -> bool:
    """True if the file sets a non-empty initial-password."""
    for m in _PASSWORD_SET.finditer(text):
        val = (m.group(1) or "").strip()
        # "auto" is documented as "generate and print" — still
        # produces a real password, so we treat it as set.
        if val and val.lower() not in {"", '""', "''"}:
            return True
    return False


def scan_text(text: str, path: str) -> List[str]:
    findings: List[str] = []
    in_rethink_file = _rethink_context(text)
    has_password = _has_password_set(text)
    lines = text.splitlines()

    def _next_value_line(idx: int) -> Tuple[int | None, str | None]:
        for j in range(idx, len(lines)):
            nxt = lines[j]
            if not nxt.strip():
                continue
            if _COMMENT_LINE.match(nxt):
                continue
            return j + 1, nxt
        return None, None

    for lineno, raw in enumerate(lines, start=1):
        if _COMMENT_LINE.match(raw):
            continue
        line = _strip_inline_comment(raw)

        # Explicit empty initial-password (always a finding,
        # context-independent — empty pwd is the "off" form).
        if _CLI_PASSWORD_EMPTY.search(line) or \
                _CONF_PASSWORD_EMPTY.match(line):
            findings.append(
                f"{path}:{lineno}: --initial-password set to empty "
                f"leaves RethinkDB admin user unauthenticated "
                f"(CWE-306/CWE-1188): {raw.strip()[:160]}"
            )
            continue

        # CLI --bind all (with same-line value)
        if _CLI_BIND_ALL.search(line) and not has_password:
            findings.append(
                f"{path}:{lineno}: rethinkdb --bind all without "
                f"--initial-password exposes the HTTP admin UI on "
                f":8080 with empty default password "
                f"(CWE-306/CWE-668): {raw.strip()[:160]}"
            )
            continue

        # CLI list-form: --bind on this line, value on next
        if in_rethink_file and _CLI_BIND_BARE.search(line) \
                and not _CLI_BIND_ALL.search(line) and not has_password:
            _, nxt_raw = _next_value_line(lineno)
            if nxt_raw is not None:
                nxt = _strip_inline_comment(nxt_raw)
                vm = re.search(
                    r"""[-\s]*['"]?all['"]?\b""",
                    nxt,
                    re.IGNORECASE,
                )
                if vm:
                    findings.append(
                        f"{path}:{lineno}: rethinkdb --bind "
                        f"(list-form) set to 'all' without "
                        f"--initial-password (CWE-306/CWE-668): "
                        f"{raw.strip()[:160]}"
                    )
                    continue

        # rethinkdb.conf bind=all without password
        if in_rethink_file and _CONF_BIND_ALL.match(line) \
                and not has_password:
            findings.append(
                f"{path}:{lineno}: rethinkdb.conf bind=all without "
                f"initial-password leaves admin UI on :8080 "
                f"unauthenticated (CWE-306/CWE-668): "
                f"{raw.strip()[:160]}"
            )
            continue

    return findings


_TARGET_NAMES = (
    "dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
    "rethinkdb.conf",
)
_TARGET_EXTS = (
    ".yaml", ".yml", ".sh", ".bash", ".service", ".tpl", ".env",
    ".conf",
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
