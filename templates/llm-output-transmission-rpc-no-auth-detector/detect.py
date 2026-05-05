#!/usr/bin/env python3
"""
llm-output-transmission-rpc-no-auth-detector

Flags Transmission BitTorrent daemon configurations that expose the
RPC interface without authentication, or that bind it to a public
interface with `rpc-whitelist-enabled` disabled. Transmission's RPC
endpoint can add torrents, change the download directory (which
enables arbitrary file write under the daemon's UID), and execute a
configured `script-torrent-done-filename`. An unauthenticated RPC on
a routable interface is a remote code execution primitive.

Maps to:
- CWE-306: Missing Authentication for Critical Function.
- CWE-1188: Insecure Default Initialization of Resource.
- CWE-284: Improper Access Control.

Stdlib-only. Reads files passed on argv (recurses into dirs and picks
settings.json, *.json, *.conf, *.ini, Dockerfile, docker-compose.*,
*.yaml, *.yml, *.sh, *.bash, *.service, *.env).

Exit codes: 0 = no findings, 1 = findings, 2 = usage error.

Heuristic
---------
We flag any of the following textual occurrences (outside comment
lines for shell/ini-style files; JSON has no comments per spec but we
ignore lines that begin with `//` for tolerant settings.json files):

1. settings.json directive `"rpc-authentication-required": false`
   (any spacing, optionally with trailing comma).
2. settings.json directive `"rpc-whitelist-enabled": false` paired
   with `"rpc-bind-address": "0.0.0.0"` or `"::"` in the same file.
3. CLI flag `--no-auth` or `-T` to `transmission-daemon` (these
   disable RPC auth) on a command line / Dockerfile CMD / systemd
   ExecStart / k8s args.
4. Env-var override `TRANSMISSION_RPC_AUTHENTICATION_REQUIRED=false`
   used by the popular linuxserver/transmission and similar templated
   container images.

Each occurrence emits one finding line.
"""

from __future__ import annotations

import os
import re
import sys
from typing import Iterable, List

# settings.json: "rpc-authentication-required": false
_JSON_AUTH_FALSE = re.compile(
    r"""(?im)"rpc-authentication-required"\s*:\s*false\b"""
)

# settings.json: "rpc-whitelist-enabled": false
_JSON_WHITELIST_FALSE = re.compile(
    r"""(?im)"rpc-whitelist-enabled"\s*:\s*false\b"""
)

# settings.json: "rpc-bind-address": "0.0.0.0" or "::" (public bind)
_JSON_PUBLIC_BIND = re.compile(
    r"""(?im)"rpc-bind-address"\s*:\s*"(?:0\.0\.0\.0|::)"\s*"""
)

# CLI: transmission-daemon -T / --no-auth
_CLI_NO_AUTH = re.compile(
    r"""(?:^|\s)transmission-daemon\b[^\n#;]*?(?:\s-T\b|\s--no-auth\b)"""
)

# CLI: a -T or --no-auth flag on a line that also contains
# "transmission" (covers wrapper scripts, helm args, exec arrays).
_CLI_NO_AUTH_NEAR = re.compile(
    r"""(?im)^.*\btransmission[^\n]*?(?:["'\s]-T["'\s]|["'\s]--no-auth["'\s])"""
)

# Env-var override used by linuxserver/haugene templated images.
_ENV_OVERRIDE = re.compile(
    r"""(?im)^\s*(?:export\s+|-\s+)?TRANSMISSION_RPC_AUTHENTICATION_REQUIRED\s*[:=]\s*["']?false["']?\b"""
)

_COMMENT_LINE = re.compile(r"""^\s*(?:#|;|//)""")


def scan_text(text: str, path: str) -> List[str]:
    findings: List[str] = []

    # File-level pairing checks (whitelist disabled + public bind)
    has_whitelist_off = bool(_JSON_WHITELIST_FALSE.search(text))
    has_public_bind = bool(_JSON_PUBLIC_BIND.search(text))

    for lineno, raw in enumerate(text.splitlines(), start=1):
        if _COMMENT_LINE.match(raw):
            continue

        if _JSON_AUTH_FALSE.search(raw):
            findings.append(
                f"{path}:{lineno}: settings.json sets "
                f"`rpc-authentication-required: false` — Transmission "
                f"RPC is exposed without auth (CWE-306/CWE-1188): "
                f"{raw.strip()[:160]}"
            )
            continue

        if (
            has_whitelist_off
            and has_public_bind
            and _JSON_WHITELIST_FALSE.search(raw)
        ):
            findings.append(
                f"{path}:{lineno}: `rpc-whitelist-enabled: false` "
                f"combined with `rpc-bind-address: 0.0.0.0` (or `::`) "
                f"in the same settings.json removes the only host-"
                f"based access control (CWE-284): {raw.strip()[:160]}"
            )
            continue

        if _CLI_NO_AUTH.search(raw) or _CLI_NO_AUTH_NEAR.search(raw):
            findings.append(
                f"{path}:{lineno}: transmission-daemon launched with "
                f"-T / --no-auth (RPC auth disabled) "
                f"(CWE-306/CWE-1188): {raw.strip()[:160]}"
            )
            continue

        if _ENV_OVERRIDE.search(raw):
            findings.append(
                f"{path}:{lineno}: "
                f"TRANSMISSION_RPC_AUTHENTICATION_REQUIRED=false env "
                f"override templates settings.json with auth disabled "
                f"(CWE-306/CWE-284): {raw.strip()[:160]}"
            )
            continue

    return findings


_TARGET_NAMES = (
    "dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
    "settings.json",
)
_TARGET_EXTS = (
    ".json", ".conf", ".ini", ".yaml", ".yml", ".sh", ".bash",
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
