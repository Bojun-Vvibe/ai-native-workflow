#!/usr/bin/env python3
"""
llm-output-dragonfly-requirepass-empty-detector

Flags **DragonflyDB** (the in-memory, Redis-protocol-compatible
datastore from dragonflydb.io) deployments that are started **without
a `--requirepass` value**, leaving the data plane open to anyone who
can reach port 6379.

Dragonfly speaks the Redis wire protocol. By default, with no
`--requirepass` set, every connecting client gets full RW access:
`FLUSHALL`, `KEYS *`, `SET`, `DEBUG SLEEP`, `MEMORY USAGE`, every
admin command. The official Dragonfly docs say it explicitly:

> "If `--requirepass` is not set, the server accepts unauthenticated
>  connections."
>  -- https://www.dragonflydb.io/docs/managing-dragonfly/authentication

Because Dragonfly's quickstart docker-compose example is literally:

    services:
      dragonfly:
        image: docker.dragonflydb.io/dragonflydb/dragonfly
        ports: ["6379:6379"]

— with no requirepass — every "self-hosted Dragonfly" tutorial copies
the same shape, and LLMs reproduce it verbatim.

Dragonfly maintainers have repeatedly warned that thousands of
internet-exposed Dragonfly instances are unauthenticated, and shodan
queries for `redis_version` + Dragonfly's banner show the same
ransom-note pattern as historical unauthenticated Redis.

Maps to:
  - CWE-306: Missing Authentication for Critical Function
  - CWE-1188: Insecure Default Initialization of Resource
  - CWE-862: Missing Authorization
  - OWASP A05:2021 Security Misconfiguration

Heuristic
---------
We look for Dragonfly invocations and flag them when **no
`--requirepass=<non-empty>`** is present. We only flag inputs that
clearly reference Dragonfly so we do not collide with vanilla Redis
detectors.

Concrete forms:

1. **CLI / shell / Dockerfile CMD / docker-compose `command:` / k8s
   `args:` / systemd `ExecStart=`** that runs `dragonfly` (binary
   name) or pulls `dragonflydb/dragonfly` image:

     dragonfly --bind 0.0.0.0
     dragonfly --requirepass=
     dragonfly --requirepass ""
     ExecStart=/usr/bin/dragonfly --port 6379

2. **docker-compose / k8s manifests** that use the
   `docker.dragonflydb.io/dragonflydb/dragonfly` image and set NO
   `--requirepass=<value>` anywhere in `command:` / `args:` /
   `entrypoint:`.

3. **Explicit empty / placeholder values**:

     --requirepass=
     --requirepass ""
     --requirepass=changeme
     --requirepass=password
     --requirepass=admin
     --requirepass=dragonfly

We do NOT flag:

  - Vanilla Redis (`redis-server`, `image: redis:*`) — covered by a
    separate detector in this chain.
  - Comments / docs that mention Dragonfly without an actual
    invocation.
  - Dragonfly invocations that include `--requirepass=<non-trivial>`
    (>= 12 chars, not a known weak placeholder).

Stdlib-only. Walks dirs, scans `*.yml`, `*.yaml`, `*.toml`, `*.conf`,
`*.ini`, `*.sh`, `*.bash`, `*.service`, `Dockerfile*`,
`docker-compose.*`, and any file whose basename contains `dragonfly`.

Exit codes: 0 = clean, 1 = findings, 2 = usage error.
"""

from __future__ import annotations

import os
import re
import sys
from typing import Iterable, List, Tuple

_DRAGONFLY_IMAGE = re.compile(
    r"""(?:image\s*[:=]\s*["']?|FROM\s+)
        [A-Za-z0-9./_\-]*dragonfly(?:db)?[A-Za-z0-9./_\-]*""",
    re.IGNORECASE | re.VERBOSE,
)

_DRAGONFLY_BIN = re.compile(
    r"""(?<![A-Za-z0-9_-])dragonfly(?:db)?(?:[ \t"']|$)""",
    re.IGNORECASE,
)

# Match: --requirepass=VAL, --requirepass VAL, --requirepass "VAL",
# JSON-array CMD form `"--requirepass", "VAL"`, equals form
# `--requirepass=`. The val capture stops at quote/whitespace/comma.
_REQUIREPASS_FLAG = re.compile(
    r"""--requirepass(?:\s*=\s*|["']?\s*[,]?\s*["']?|\s+["']?)
        (?P<val>[^"'\s,\]]*)""",
    re.IGNORECASE | re.VERBOSE,
)

_WEAK_PASSWORDS = {
    "", "''", '""',
    "password", "passwd", "pass",
    "admin", "root", "guest",
    "dragonfly", "dragonflydb",
    "changeme", "change-me", "changeit",
    "redis", "secret", "test", "demo", "default",
    "12345", "123456", "1234567", "12345678", "123456789", "1234567890",
    "qwerty", "letmein", "welcome",
}

_COMMENT_LINE = re.compile(r"""^\s*[#;]""")


def _strip_quotes(s: str) -> str:
    if len(s) >= 2 and s[0] == s[-1] and s[0] in "'\"":
        return s[1:-1]
    return s


def _password_is_weak(raw: str) -> bool:
    v = _strip_quotes(raw).strip()
    if v == "":
        return True
    if v.lower() in _WEAK_PASSWORDS:
        return True
    # Very short passwords (< 12 chars) for an internet-exposed K/V
    # service are effectively "no auth" against online brute force.
    if len(v) < 12:
        return True
    return False


def _file_mentions_dragonfly(text: str) -> bool:
    if _DRAGONFLY_IMAGE.search(text):
        return True
    if re.search(r"""dragonfly(?:db)?""", text, re.IGNORECASE):
        # Need an actual binary invocation or image, not just a doc
        # mention. Look for one of:
        #   - dragonfly binary token
        #   - dragonflydb/ in any line
        for line in text.splitlines():
            if _COMMENT_LINE.match(line):
                continue
            if _DRAGONFLY_BIN.search(line):
                return True
            if "dragonflydb/" in line.lower():
                return True
    return False


def _scan_requirepass(text: str, path: str) -> List[Tuple[int, str, str]]:
    """Return list of (lineno, kind, raw_line) findings.

    kind in {"missing", "empty", "weak:<value>"}.
    """
    findings: List[Tuple[int, str, str]] = []
    saw_dragonfly_invocation = False
    saw_strong_pass = False
    weak_hits: List[Tuple[int, str, str]] = []

    for lineno, raw in enumerate(text.splitlines(), start=1):
        if _COMMENT_LINE.match(raw):
            continue
        line_low = raw.lower()
        is_invocation = (
            _DRAGONFLY_BIN.search(raw) is not None
            or "dragonflydb/" in line_low
            or _DRAGONFLY_IMAGE.search(raw) is not None
        )
        if is_invocation:
            saw_dragonfly_invocation = True

        m = _REQUIREPASS_FLAG.search(raw)
        if m:
            val = m.group("val")
            if _password_is_weak(val):
                weak_hits.append((lineno, _strip_quotes(val), raw.strip()))
            else:
                saw_strong_pass = True

    out: List[Tuple[int, str, str]] = []
    if not saw_dragonfly_invocation:
        return out

    if weak_hits:
        for lineno, val, raw_line in weak_hits:
            kind = "empty" if val == "" else f"weak:{val}"
            out.append((lineno, kind, raw_line))
        return out

    if not saw_strong_pass:
        # Find first invocation line for the report anchor.
        anchor = 1
        for lineno, raw in enumerate(text.splitlines(), start=1):
            if _COMMENT_LINE.match(raw):
                continue
            if (
                _DRAGONFLY_BIN.search(raw)
                or "dragonflydb/" in raw.lower()
                or _DRAGONFLY_IMAGE.search(raw)
            ):
                anchor = lineno
                break
        out.append((anchor, "missing", ""))
    return out


def scan(path: str) -> List[str]:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
    except OSError as e:
        sys.stderr.write(f"warn: cannot read {path}: {e}\n")
        return []

    if not _file_mentions_dragonfly(text):
        return []

    out: List[str] = []
    for lineno, kind, raw_line in _scan_requirepass(text, path):
        if kind == "missing":
            out.append(
                f"{path}:{lineno}: dragonfly invocation has no "
                f"--requirepass flag -> redis-protocol DB on :6379 "
                f"accepts unauthenticated FLUSHALL/KEYS/SET "
                f"(CWE-306/CWE-1188)"
            )
        elif kind == "empty":
            out.append(
                f"{path}:{lineno}: dragonfly --requirepass set to empty "
                f"value -> auth is effectively off (CWE-306/CWE-1188): "
                f"{raw_line[:160]}"
            )
        elif kind.startswith("weak:"):
            val = kind[len("weak:"):]
            out.append(
                f"{path}:{lineno}: dragonfly --requirepass uses weak/"
                f"placeholder value {val!r} -> trivially brute-forced "
                f"(CWE-521/CWE-1392): {raw_line[:160]}"
            )
    return out


_TARGET_EXTS = (
    ".yml", ".yaml", ".toml", ".conf", ".ini",
    ".sh", ".bash", ".service", ".dockerfile", ".env.example",
)


def iter_paths(roots: Iterable[str]) -> Iterable[str]:
    for r in roots:
        if os.path.isdir(r):
            for dp, _dn, fn in os.walk(r):
                for f in fn:
                    low = f.lower()
                    if (
                        "dragonfly" in low
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
