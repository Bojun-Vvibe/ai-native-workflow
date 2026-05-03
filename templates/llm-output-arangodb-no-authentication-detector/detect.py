#!/usr/bin/env python3
"""
llm-output-arangodb-no-authentication-detector

Flags ArangoDB configurations / invocations that disable
authentication on the arangod server.

Maps to:
- CWE-306: Missing Authentication for Critical Function.
- CWE-1188: Insecure Default Initialization of Resource.
- CWE-732: Incorrect Permission Assignment for Critical Resource.

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

# --server.authentication false  /  --server.authentication=false
_CLI_AUTH_FALSE = re.compile(
    r"""--server\.authentication(?:[=\s]+)['"]?(false|0|no|off)['"]?\b""",
    re.IGNORECASE,
)

# Bare flag (list-form: value on next list item)
_CLI_AUTH_BARE = re.compile(r"""--server\.authentication\b""")

# arangod.conf: under [server] block, "authentication = false"
# We don't truly track INI sections; we accept any "authentication"
# key on its own line set to a falsy value, AND the file context
# must look like an arangod conf (presence of [server] or known
# arangod keys).
_CONF_AUTH = re.compile(
    r"""^\s*authentication\s*[:=]\s*['"]?(false|0|no|off)['"]?\s*$""",
    re.IGNORECASE,
)

# Env override
_ENV_NO_AUTH = re.compile(
    r"""(?im)^\s*(?:export\s+|-\s+)?ARANGO_NO_AUTH\s*[:=]\s*['"]?(?:1|true|yes|on)['"]?\b"""
)

# docker-compose / k8s env list form: "ARANGO_NO_AUTH=1" or as
# - name: ARANGO_NO_AUTH
#   value: "1"
_ENV_LIST_NAME = re.compile(
    r"""(?i)\bARANGO_NO_AUTH\b"""
)

_COMMENT_LINE = re.compile(r"""^\s*#""")

_ARANGO_CTX = re.compile(
    r"""(?i)\barango(?:d|db)?\b|\barangodb/|image:\s*['"]?arango|\[server\]"""
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


def _arango_context(text: str) -> bool:
    return bool(_ARANGO_CTX.search(text))


def scan_text(text: str, path: str) -> List[str]:
    findings: List[str] = []
    in_arango_file = _arango_context(text)
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

        # Env override (any file)
        if _ENV_NO_AUTH.search(line):
            findings.append(
                f"{path}:{lineno}: ARANGO_NO_AUTH=1 disables ArangoDB "
                f"authentication; any client reaching :8529 has "
                f"administrative access (CWE-306/CWE-1188): "
                f"{raw.strip()[:160]}"
            )
            continue

        # k8s/compose env list pair: name: ARANGO_NO_AUTH on this line,
        # value on the next non-blank line.
        if in_arango_file and _ENV_LIST_NAME.search(line) and \
                "=" not in line and "no_auth" not in line.lower().split("arango_no_auth", 1)[0]:
            # Look for `value: "1"` on a near-by line (within 3 lines).
            for j in range(lineno, min(lineno + 3, len(lines))):
                nxt = lines[j]
                vm = re.search(
                    r"""(?i)\bvalue\s*:\s*['"]?(1|true|yes|on)['"]?""",
                    nxt,
                )
                if vm:
                    findings.append(
                        f"{path}:{lineno}: ARANGO_NO_AUTH env (k8s "
                        f"list form) set to {vm.group(1)!r} disables "
                        f"ArangoDB authentication (CWE-306/CWE-1188): "
                        f"{raw.strip()[:160]}"
                    )
                    break
            else:
                pass
            # don't `continue` — also let other rules fire on this line

        # CLI flag with value on same line
        if _CLI_AUTH_FALSE.search(line):
            findings.append(
                f"{path}:{lineno}: --server.authentication false "
                f"disables ArangoDB authentication (CWE-306/CWE-1188): "
                f"{raw.strip()[:160]}"
            )
            continue

        # CLI flag in list-form (value on next list element)
        if in_arango_file and _CLI_AUTH_BARE.search(line) \
                and not _CLI_AUTH_FALSE.search(line):
            _, nxt_raw = _next_value_line(lineno)
            if nxt_raw is not None:
                nxt = _strip_inline_comment(nxt_raw)
                vm = re.search(
                    r"""[-\s]*['"]?(false|0|no|off)['"]?\b""",
                    nxt,
                    re.IGNORECASE,
                )
                if vm:
                    findings.append(
                        f"{path}:{lineno}: --server.authentication "
                        f"(list-form) set to {vm.group(1)!r} disables "
                        f"ArangoDB authentication (CWE-306/CWE-1188): "
                        f"{raw.strip()[:160]}"
                    )
                    continue

        # arangod.conf [server] block
        if in_arango_file and _CONF_AUTH.match(line):
            findings.append(
                f"{path}:{lineno}: arangod.conf authentication = "
                f"false disables auth (CWE-306/CWE-1188): "
                f"{raw.strip()[:160]}"
            )
            continue

    return findings


_TARGET_NAMES = (
    "dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
    "arangod.conf",
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
