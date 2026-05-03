#!/usr/bin/env python3
"""
llm-output-caddy-admin-api-public-bind-detector

Flags Caddy server configurations that expose the **admin API** on a
non-loopback address. By default Caddy binds its admin API to
`localhost:2019`. The admin API is **unauthenticated** and lets any
caller load arbitrary configuration, including new reverse-proxy
upstreams, TLS keys, and exec'd handlers. Binding it to `0.0.0.0`,
`[::]`, `tcp/<public-ip>`, or any non-loopback host effectively gives
full server takeover to anyone who can reach the port.

Maps to:
- CWE-306: Missing Authentication for Critical Function
- CWE-668: Exposure of Resource to Wrong Sphere
- CWE-1188: Insecure Default Initialization of Resource (when the
  default localhost binding is overridden without adding an
  authenticator in front)

LLMs reach for `admin 0.0.0.0:2019` because containerized Caddy
tutorials say "you can't curl the admin API from another container
unless you bind it to all interfaces". The tutorials never mention
that Caddy's admin API has no auth at all.

Stdlib-only. Reads files passed on argv (recurses into dirs and picks
Caddyfile, *.caddyfile, *.json, *.yaml, *.yml, Dockerfile, *.sh).

Exit codes: 0 = no findings, 1 = findings, 2 = usage error.

Heuristic
---------
We flag any of the following, outside `#` / `//` comments:

1. Caddyfile global block: `admin <host>:<port>` where host is not
   `localhost`, `127.0.0.1`, `[::1]`, or `unix/`. `admin off` is
   ignored (that disables the API).
2. JSON config: `"admin": { "listen": "<host>:<port>" }` with a
   non-loopback host.
3. CLI invocation: `caddy run ... --resume --watch ... --address ...`
   or `caddy adapt --address 0.0.0.0:2019` style flags binding the
   admin endpoint to a public address.
4. Env var `CADDY_ADMIN=<host>:<port>` with a non-loopback host.
"""

from __future__ import annotations

import os
import re
import sys
from typing import Iterable, List

_LOOPBACK_HOSTS = {
    "localhost",
    "127.0.0.1",
    "[::1]",
    "::1",
}


def _is_loopback(host: str) -> bool:
    h = host.strip().strip('"').strip("'")
    if not h:
        return True
    if h.startswith("unix/"):
        return True
    return h in _LOOPBACK_HOSTS


# Caddyfile: `admin <host>:<port>` (host part may be empty meaning all).
# Examples:
#   admin 0.0.0.0:2019
#   admin :2019
#   admin off
#   admin localhost:2019
_CADDYFILE_ADMIN = re.compile(
    r"""^\s*admin\s+(?P<addr>\S+)"""
)

# JSON: "admin": { ... "listen": "host:port" ... }
# We do this loose because we don't want to parse the whole JSON tree.
_JSON_ADMIN_LISTEN = re.compile(
    r'"admin"\s*:\s*\{[^}]*"listen"\s*:\s*"(?P<addr>[^"]+)"',
    re.DOTALL,
)

# CLI: --address <addr> or -address <addr> on a caddy command line.
_CLI_ADDRESS = re.compile(
    r"""\bcaddy\b[^\n#]*?--?address[= ]+(?P<addr>\S+)"""
)

# Env var assignment.
_ENV_ADMIN = re.compile(
    r"""\bCADDY_ADMIN\s*[:=]\s*['"]?(?P<addr>[^\s'"]+)"""
)

_COMMENT_LINE = re.compile(r"""^\s*(#|//)""")


def _split_host_port(addr: str) -> str:
    a = addr.strip().strip('"').strip("'")
    if a.lower() == "off":
        return "off"
    # IPv6 in brackets: [::1]:2019
    if a.startswith("["):
        end = a.find("]")
        if end != -1:
            return a[: end + 1]
    # host:port
    if ":" in a:
        return a.rsplit(":", 1)[0]
    return a


def scan_text(text: str, path: str) -> List[str]:
    findings: List[str] = []

    # Pass 1: line-oriented Caddyfile / CLI / env scans.
    for lineno, raw in enumerate(text.splitlines(), start=1):
        if _COMMENT_LINE.match(raw):
            continue
        line = raw.split("#", 1)[0]

        m = _CADDYFILE_ADMIN.match(line)
        if m:
            addr = m.group("addr")
            host = _split_host_port(addr)
            if host == "off":
                pass  # admin disabled; safe
            elif host == "" or not _is_loopback(host):
                # `admin :2019` (empty host) means bind all interfaces.
                findings.append(
                    f"{path}:{lineno}: Caddy admin API bound to "
                    f"non-loopback address `{addr}` "
                    f"(CWE-306/CWE-668, unauthenticated control plane): "
                    f"{raw.strip()[:160]}"
                )
                continue

        m = _CLI_ADDRESS.search(line)
        if m and "admin" in line.lower():
            addr = m.group("addr")
            host = _split_host_port(addr)
            if host == "" or not _is_loopback(host):
                findings.append(
                    f"{path}:{lineno}: caddy CLI binds admin API to "
                    f"`{addr}` (CWE-306/CWE-668): {raw.strip()[:160]}"
                )
                continue

        m = _ENV_ADMIN.search(line)
        if m:
            addr = m.group("addr")
            host = _split_host_port(addr)
            if host == "off":
                pass
            elif host == "" or not _is_loopback(host):
                findings.append(
                    f"{path}:{lineno}: CADDY_ADMIN env binds admin "
                    f"API to `{addr}` (CWE-306/CWE-668): "
                    f"{raw.strip()[:160]}"
                )
                continue

    # Pass 2: JSON config (multiline). Report at the line of `"listen"`.
    for m in _JSON_ADMIN_LISTEN.finditer(text):
        addr = m.group("addr")
        host = _split_host_port(addr)
        if host == "off":
            continue
        if host == "" or not _is_loopback(host):
            # Locate the `listen` substring's line for nicer output.
            listen_pos = text.find('"listen"', m.start())
            if listen_pos == -1:
                listen_pos = m.start()
            lineno = text.count("\n", 0, listen_pos) + 1
            findings.append(
                f"{path}:{lineno}: Caddy JSON admin.listen = "
                f"`{addr}` (CWE-306/CWE-668, unauthenticated "
                f"control plane bound to non-loopback)"
            )

    return findings


_TARGET_NAMES = (
    "caddyfile",
    "dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
)
_TARGET_EXTS = (
    ".caddyfile", ".json", ".yaml", ".yml",
    ".sh", ".bash", ".service", ".conf",
)


def iter_paths(roots: Iterable[str]) -> Iterable[str]:
    for r in roots:
        if os.path.isdir(r):
            for dp, _dn, fn in os.walk(r):
                for f in fn:
                    low = f.lower()
                    if low in _TARGET_NAMES or low.startswith("dockerfile") or low.startswith("caddyfile"):
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
