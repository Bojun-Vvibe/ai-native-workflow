#!/usr/bin/env python3
"""
llm-output-trino-http-server-authentication-type-none-detector

Flags Trino (and the legacy PrestoSQL fork) coordinator
configurations that disable HTTP authentication on the coordinator,
either by omitting `http-server.authentication.type` while leaving
`http-server.authentication.allow-insecure-over-http=true`, or by
setting the type explicitly to `NONE`.

Trino's coordinator (default port 8080 for HTTP, 8443 for HTTPS)
exposes:

- the `/v1/statement` endpoint that runs SQL as whichever user
  the client claims to be (the `X-Trino-User` HTTP header is
  trusted verbatim when no authenticator is wired in),
- the `/v1/jmx`, `/v1/node`, `/v1/thread`, and `/v1/info` endpoints
  that leak cluster topology, JVM internals, and version info,
- the management endpoints under `/v1/cluster` and `/ui/` that can
  kill running queries.

When `http-server.authentication.type` is unset (or set to `NONE`)
and the coordinator listens on a routable interface, anyone who can
reach port 8080 can run SQL as `root` / `admin` / any chosen user.

Maps to:
- CWE-306: Missing Authentication for Critical Function.
- CWE-287: Improper Authentication (the X-Trino-User header is
  accepted without proof of identity).

Stdlib-only. Reads files passed on argv (recurses into dirs and
picks config.properties, coordinator.properties, *.properties,
*.conf, *.yaml, *.yml, *.sh, *.bash, *.tf, and Dockerfile-like
files).

Heuristic
---------
We flag, outside `#` / `//` comments:

1. `http-server.authentication.type` set to a value containing
   `NONE` (case-insensitive). Trino accepts a comma-separated list
   like `PASSWORD,JWT`; we flag only when `NONE` appears in the
   list (or is the only value).
2. `http-server.authentication.allow-insecure-over-http=true` --
   this only matters if the coordinator is on plain HTTP, but in
   combination with no TLS it indicates the operator has explicitly
   accepted unauthenticated/plaintext access.
3. Helm / YAML form: `coordinator.config."http-server.authentication.type": "NONE"`.
4. CLI / env form: `TRINO_HTTP_SERVER_AUTHENTICATION_TYPE=NONE`
   (Trino reads `TRINO_*` and `PRESTO_*` env overrides through its
   launcher script).

Each occurrence emits one finding line. Exit codes:
  0 = no findings, 1 = findings, 2 = usage error.
"""

from __future__ import annotations

import os
import re
import sys
from typing import Iterable, List

# Trino properties form: dotted keys, value after `=` or `:`.
# `http-server.authentication.type=NONE` (case-insensitive value).
_AUTH_TYPE_KV = re.compile(
    r"""(?P<key>\bhttp-server\.authentication\.type)"""
    r"""\s*[:=]\s*['"]?(?P<val>[A-Za-z0-9_,\- ]+?)['"]?\s*(?:#.*)?$""",
    re.MULTILINE,
)

# `http-server.authentication.allow-insecure-over-http=true`
_INSECURE_OVER_HTTP = re.compile(
    r"""(?P<key>\bhttp-server\.authentication\.allow-insecure-over-http)"""
    r"""\s*[:=]\s*['"]?(?P<val>[A-Za-z0-9_]+)['"]?"""
)

# Env-var override form via the launcher: TRINO_HTTP_SERVER_AUTHENTICATION_TYPE=NONE
# (also legacy PRESTO_*).
_ENV = re.compile(
    r"""\b(?:TRINO|PRESTO)_HTTP_SERVER_AUTHENTICATION_TYPE"""
    r"""\s*[:=]\s*['"]?(?P<val>[A-Za-z0-9_,\- ]+?)['"]?\s*$""",
    re.MULTILINE,
)

_TRUTHY = {"true", "1", "yes", "on"}

_COMMENT_LINE = re.compile(r"""^\s*(#|//)""")


def _strip_comment(line: str) -> str:
    out = []
    in_s = False
    in_d = False
    i = 0
    while i < len(line):
        ch = line[i]
        if ch == "'" and not in_d:
            in_s = not in_s
        elif ch == '"' and not in_s:
            in_d = not in_d
        elif ch == "#" and not in_s and not in_d:
            break
        elif (
            ch == "/"
            and i + 1 < len(line)
            and line[i + 1] == "/"
            and not in_s
            and not in_d
        ):
            break
        out.append(ch)
        i += 1
    return "".join(out)


def _value_is_none(val: str) -> bool:
    """Trino allows a comma-list; flag when NONE appears at all."""
    parts = [p.strip().upper() for p in val.split(",")]
    return "NONE" in parts


def scan_text(text: str, path: str) -> List[str]:
    findings: List[str] = []
    for lineno, raw in enumerate(text.splitlines(), start=1):
        if _COMMENT_LINE.match(raw):
            continue
        line = _strip_comment(raw)

        for m in _AUTH_TYPE_KV.finditer(line):
            if _value_is_none(m.group("val")):
                findings.append(
                    f"{path}:{lineno}: {m.group('key')}=NONE "
                    f"(CWE-306/CWE-287, Trino coordinator accepts "
                    f"X-Trino-User without authentication): "
                    f"{raw.strip()[:160]}"
                )

        for m in _INSECURE_OVER_HTTP.finditer(line):
            if m.group("val").lower() in _TRUTHY:
                findings.append(
                    f"{path}:{lineno}: {m.group('key')}=true "
                    f"(CWE-319/CWE-287, Trino coordinator allows "
                    f"unauthenticated plaintext HTTP): "
                    f"{raw.strip()[:160]}"
                )

        for m in _ENV.finditer(line):
            if _value_is_none(m.group("val")):
                findings.append(
                    f"{path}:{lineno}: TRINO/PRESTO env override sets "
                    f"http-server.authentication.type=NONE "
                    f"(CWE-306): {raw.strip()[:160]}"
                )
    return findings


_TARGET_NAMES = (
    "config.properties",
    "coordinator.properties",
    "worker.properties",
    "node.properties",
)
_TARGET_EXTS = (
    ".properties", ".conf", ".yaml", ".yml",
    ".sh", ".bash", ".tpl", ".tf", ".env",
)


def iter_paths(roots: Iterable[str]) -> Iterable[str]:
    for r in roots:
        if os.path.isdir(r):
            for dp, _dn, fn in os.walk(r):
                for f in fn:
                    low = f.lower()
                    if low in _TARGET_NAMES or low.endswith(_TARGET_EXTS):
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
