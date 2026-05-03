#!/usr/bin/env python3
"""
llm-output-redis-protected-mode-no-detector

Flags Redis configurations that disable `protected-mode`. Redis ships
with `protected-mode yes` since 3.2.0 specifically because countless
unauthenticated, internet-exposed Redis instances were being wormed
(see "redis-cli FLUSHALL" / Fairware-style ransom notes circa 2017).

Protected mode refuses connections from non-loopback clients when
*all* of the following are true:

  * the server has no `requirepass` set, AND
  * the server has no ACL users with passwords, AND
  * the listening address is not bound to a single explicit interface.

When an LLM (or a copy-pasted "fix this Redis won't connect" Stack
Overflow answer) sets `protected-mode no`, the safety net is gone and
*any* network reachability + missing auth = full RCE via Lua /
`CONFIG SET dir` + `SAVE`.

Maps to:
- CWE-306: Missing Authentication for Critical Function.
- CWE-1188: Insecure Default Initialization of Resource (the safe
  default is `yes`; `no` is a deliberate downgrade).
- CWE-284: Improper Access Control.

Stdlib-only. Reads files passed on argv (recurses into dirs and picks
redis.conf, *.conf, *.cnf, Dockerfile, docker-compose.*, *.yaml,
*.yml, *.sh, *.bash, *.service, Helm template files).

Exit codes: 0 = no findings, 1 = findings, 2 = usage error.

Heuristic
---------
We flag any of the following textual occurrences (outside `#` comment
lines):

1. `protected-mode no` or `protected-mode  no` in a redis.conf-style
   directive line.
2. `--protected-mode no` on a `redis-server` command line (Dockerfile
   CMD/ENTRYPOINT, shell wrapper, systemd ExecStart, k8s args).
3. `CONFIG SET protected-mode no` issued at runtime via `redis-cli`.
4. Exec-array form: `["redis-server", "...", "--protected-mode", "no"]`
   (k8s container args / docker-compose command).

Each occurrence emits one finding line.
"""

from __future__ import annotations

import os
import re
import sys
from typing import Iterable, List

# redis.conf directive: `protected-mode no`
_CONF_DIRECTIVE = re.compile(
    r"""(?im)^\s*protected-mode\s+no\b"""
)

# CLI flag: `--protected-mode no` (also tolerates `=no`)
_CLI_FLAG = re.compile(
    r"""--protected-mode(?:\s+|=)["']?no["']?\b"""
)

# `CONFIG SET protected-mode no` (case-insensitive Redis command)
_RUNTIME_SET = re.compile(
    r"""(?i)\bCONFIG\s+SET\s+protected-mode\s+["']?no["']?\b"""
)

# Exec-array form: ["redis-server", ..., "--protected-mode", "no", ...]
# We require both tokens in the same array literal.
_EXEC_ARRAY = re.compile(
    r"""\[[^\]]*["']redis-server["'][^\]]*"""
    r"""["']--protected-mode["']\s*,\s*["']no["'][^\]]*\]"""
)

_COMMENT_LINE = re.compile(r"""^\s*#""")


def _strip_inline_comment(line: str) -> str:
    """Strip trailing `#` comments outside quotes (best effort)."""
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


def scan_text(text: str, path: str) -> List[str]:
    findings: List[str] = []
    for lineno, raw in enumerate(text.splitlines(), start=1):
        if _COMMENT_LINE.match(raw):
            continue
        line = _strip_inline_comment(raw)

        if _CONF_DIRECTIVE.search(line):
            findings.append(
                f"{path}:{lineno}: redis.conf directive `protected-mode no` "
                f"disables Redis safety net (CWE-306/CWE-1188): "
                f"{raw.strip()[:160]}"
            )
            continue
        if _EXEC_ARRAY.search(line):
            findings.append(
                f"{path}:{lineno}: exec-array launches redis-server with "
                f"--protected-mode no (CWE-306/CWE-1188): "
                f"{raw.strip()[:160]}"
            )
            continue
        if _CLI_FLAG.search(line):
            findings.append(
                f"{path}:{lineno}: redis-server invoked with "
                f"--protected-mode no (CWE-306/CWE-1188): "
                f"{raw.strip()[:160]}"
            )
            continue
        if _RUNTIME_SET.search(line):
            findings.append(
                f"{path}:{lineno}: runtime `CONFIG SET protected-mode no` "
                f"disables safety net (CWE-306/CWE-284): "
                f"{raw.strip()[:160]}"
            )
            continue
    return findings


_TARGET_NAMES = (
    "dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
    "redis.conf",
)
_TARGET_EXTS = (
    ".conf", ".cnf", ".yaml", ".yml", ".sh", ".bash",
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
