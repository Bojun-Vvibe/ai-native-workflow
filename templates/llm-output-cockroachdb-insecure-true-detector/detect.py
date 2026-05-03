#!/usr/bin/env python3
"""
llm-output-cockroachdb-insecure-true-detector

Flags CockroachDB invocations that start the node in insecure mode
(`cockroach start --insecure`, `cockroach start-single-node
--insecure`, `cockroach demo --insecure`, or COCKROACH_INSECURE=true
in env). Insecure mode disables TLS for both inter-node and SQL
client connections AND disables password authentication for `root`.

Maps to:
- CWE-319: Cleartext Transmission of Sensitive Information.
- CWE-306: Missing Authentication for Critical Function.
- CWE-1188: Insecure Default Initialization of Resource.

Stdlib-only. Reads files passed on argv (recurses into dirs and picks
Dockerfile, docker-compose.*, *.yaml, *.yml, *.sh, *.bash, *.service,
*.env, Helm template files).

Exit codes: 0 = no findings, 1 = findings, 2 = usage error.

Heuristic
---------
We flag any of the following textual occurrences (outside `#`
comment lines):

1. `cockroach <subcmd> ... --insecure` on a shell command line where
   <subcmd> is one of `start`, `start-single-node`, `demo`, `sql`,
   `node`, `init`, `connect`. Order of flag vs. other args is
   tolerated by anchoring on `cockroach\b` and then scanning the
   rest of the line for `--insecure\b`.
2. Exec-array form: ["cockroach", "<subcmd>", ..., "--insecure", ...]
   in k8s container args / docker-compose command arrays.
3. COCKROACH_INSECURE=true env override.

Each occurrence emits one finding line.
"""

from __future__ import annotations

import os
import re
import sys
from typing import Iterable, List

# Shell command line: cockroach <subcmd> ... --insecure
# We require `cockroach` to appear and `--insecure` to follow on the
# same line (tolerating intervening args).
_CLI_LINE = re.compile(
    r"""(?:^|[\s'"`/])cockroach\b[^\n#]*?--insecure\b"""
)

# docker-compose / k8s `command:` shorthand where the entrypoint is
# implicit (the official cockroach image's ENTRYPOINT is `cockroach`).
# We catch lines that pair a Cockroach subcommand keyword with the
# --insecure flag, even when the literal `cockroach` token is absent.
_SUBCMD_LINE = re.compile(
    r"""\b(?:start-single-node|start|demo|init)\b[^\n#]*?--insecure\b"""
)

# Exec-array form: ["cockroach", ..., "--insecure", ...]
_EXEC_ARRAY = re.compile(
    r"""\[[^\]]*["']cockroach["'][^\]]*["']--insecure["'][^\]]*\]"""
)

# Env override
_ENV_OVERRIDE = re.compile(
    r"""(?im)^\s*(?:export\s+)?COCKROACH_INSECURE\s*[:=]\s*["']?(?:true|1|yes)["']?\b"""
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

        if _ENV_OVERRIDE.search(raw):
            findings.append(
                f"{path}:{lineno}: COCKROACH_INSECURE=true env override "
                f"runs CockroachDB without TLS or auth (CWE-319/CWE-306): "
                f"{raw.strip()[:160]}"
            )
            continue

        line = _strip_inline_comment(raw)

        if _EXEC_ARRAY.search(line):
            findings.append(
                f"{path}:{lineno}: exec-array launches cockroach with "
                f"--insecure (CWE-319/CWE-306/CWE-1188): "
                f"{raw.strip()[:160]}"
            )
            continue
        if _CLI_LINE.search(line):
            findings.append(
                f"{path}:{lineno}: cockroach invoked with --insecure "
                f"(no TLS, no auth) (CWE-319/CWE-306/CWE-1188): "
                f"{raw.strip()[:160]}"
            )
            continue
        if _SUBCMD_LINE.search(line):
            findings.append(
                f"{path}:{lineno}: cockroach subcommand line uses "
                f"--insecure (no TLS, no auth) (CWE-319/CWE-306): "
                f"{raw.strip()[:160]}"
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
