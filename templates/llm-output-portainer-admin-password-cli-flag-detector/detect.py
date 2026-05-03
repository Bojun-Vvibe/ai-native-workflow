#!/usr/bin/env python3
"""
llm-output-portainer-admin-password-cli-flag-detector

Flags Portainer server invocations that pass the initial admin
password on the command line (--admin-password / --admin-password=)
or via a non-secret-mount --admin-password-file path, and flags the
well-known `tryportainer` bcrypt demo hash anywhere in the input.

Maps to:
- CWE-256: Plaintext Storage of a Password.
- CWE-214: Invocation of Process Using Visible Sensitive Information.
- CWE-798: Use of Hard-coded Credentials.

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

# --admin-password VALUE  or  --admin-password=VALUE
_ADMIN_PW = re.compile(
    r"""--admin-password(?:[=\s]+)(['"]?)([^\s'"\]]+)\1"""
)

# --admin-password-file VALUE  or  --admin-password-file=VALUE
_ADMIN_PW_FILE = re.compile(
    r"""--admin-password-file(?:[=\s]+)(['"]?)([^\s'"\]]+)\1"""
)

# Bare flag occurrence (covers YAML/JSON list-form args where the
# value is on the next list element).
_ADMIN_PW_BARE = re.compile(r"""--admin-password\b(?!-file)""")
_ADMIN_PW_FILE_BARE = re.compile(r"""--admin-password-file\b""")

# The well-known demo bcrypt hash from the Portainer quickstart docs
# (the bcrypt of "tryportainer"). Match the stable prefix so cost
# parameter changes are still caught.
_DEMO_BCRYPT = re.compile(
    r"""\$2[aby]\$05\$qLJDZi6eY6WG\.Yk7YQk6T\."""
)

# Lines that look like they are invoking portainer at all
_PORTAINER_CTX = re.compile(
    r"""(?i)\bportainer(?:/portainer|-ce|/agent)?\b|\bportainer:|image:\s*['"]?portainer"""
)

# Paths that ARE acceptable for --admin-password-file (real secret mounts)
_SECRET_MOUNT_PREFIXES = (
    "/run/secrets/",
    "/var/run/secrets/",
    "/etc/portainer/secrets/",
)

_COMMENT_LINE = re.compile(r"""^\s*#""")


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


def _portainer_context(text: str) -> bool:
    """Return True if the file appears to reference portainer at all."""
    return bool(_PORTAINER_CTX.search(text))


def scan_text(text: str, path: str) -> List[str]:
    findings: List[str] = []
    in_portainer_file = _portainer_context(text)
    lines = text.splitlines()

    def _next_value_line(idx: int) -> Tuple[int, str] | Tuple[None, None]:
        """Return the next non-blank, non-comment line after idx (1-based input)."""
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

        # The demo bcrypt is a hard-coded credential ANYWHERE.
        if _DEMO_BCRYPT.search(line):
            findings.append(
                f"{path}:{lineno}: well-known Portainer demo bcrypt hash "
                f"for password 'tryportainer' is hard-coded "
                f"(CWE-798/CWE-256): {raw.strip()[:160]}"
            )
            continue

        m = _ADMIN_PW.search(line)
        if m and (in_portainer_file or "portainer" in line.lower()):
            findings.append(
                f"{path}:{lineno}: --admin-password on Portainer command "
                f"line leaks via ps/docker inspect (CWE-214/CWE-256): "
                f"{raw.strip()[:160]}"
            )
            continue

        m = _ADMIN_PW_FILE.search(line)
        if m and (in_portainer_file or "portainer" in line.lower()):
            value = m.group(2)
            if not any(value.startswith(p) for p in _SECRET_MOUNT_PREFIXES):
                findings.append(
                    f"{path}:{lineno}: --admin-password-file points at "
                    f"non-secret-mount path {value!r}; use /run/secrets/* "
                    f"or k8s secret mount (CWE-256): {raw.strip()[:160]}"
                )
                continue

        # YAML/JSON list-form: the flag is on its own line, value on next.
        if in_portainer_file:
            if _ADMIN_PW_FILE_BARE.search(line) and not _ADMIN_PW_FILE.search(line):
                _, nxt_raw = _next_value_line(lineno)
                if nxt_raw is not None:
                    nxt = _strip_inline_comment(nxt_raw)
                    # Pull a quoted or bare scalar from the next list item.
                    vm = re.search(
                        r"""[-\s]*['"]?([^'"\s,\]]+)['"]?""", nxt
                    )
                    if vm:
                        value = vm.group(1)
                        if not any(value.startswith(p) for p in _SECRET_MOUNT_PREFIXES):
                            findings.append(
                                f"{path}:{lineno}: --admin-password-file "
                                f"(list-form) points at non-secret-mount "
                                f"path {value!r}; use /run/secrets/* or "
                                f"k8s secret mount (CWE-256): "
                                f"{raw.strip()[:160]}"
                            )
                            continue
            elif _ADMIN_PW_BARE.search(line) and not _ADMIN_PW.search(line):
                findings.append(
                    f"{path}:{lineno}: --admin-password (list-form) on "
                    f"Portainer args leaks via ps/docker inspect "
                    f"(CWE-214/CWE-256): {raw.strip()[:160]}"
                )
                continue
    return findings


_TARGET_NAMES = (
    "dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
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
