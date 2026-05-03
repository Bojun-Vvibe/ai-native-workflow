#!/usr/bin/env python3
"""
llm-output-kong-admin-api-public-bind-detector

Flags Kong Gateway configurations that bind the Admin API
(admin_listen / KONG_ADMIN_LISTEN / KONG_ADMIN_GUI_LISTEN) to
a non-loopback address.

Maps to:
- CWE-306: Missing Authentication for Critical Function.
- CWE-668: Exposure of Resource to Wrong Sphere.
- CWE-1188: Insecure Default Initialization of Resource.

Stdlib-only. Reads files passed on argv (recurses into dirs and picks
kong.conf, Dockerfile, docker-compose.*, *.yaml, *.yml, *.sh,
*.bash, *.service, *.env, *.tpl, *.conf).

Exit codes: 0 = no findings, 1 = findings, 2 = usage error.
"""

from __future__ import annotations

import os
import re
import sys
from typing import Iterable, List

# Match the value side of an admin_listen / KONG_ADMIN_LISTEN /
# KONG_ADMIN_GUI_LISTEN setting.  We extract the address:port (or
# bare port) and decide separately whether it is public.
_KEY_LINE = re.compile(
    r"""(?ix)
        ^\s*
        (?:export\s+|-\s+)?
        (admin_listen|KONG_ADMIN_LISTEN|KONG_ADMIN_GUI_LISTEN)
        \s*[:=]\s*
        ['"]?
        (?P<val>[^'"#\n]+?)
        ['"]?
        \s*$
    """,
)

# YAML "value:" form for k8s env list:
#   - name: KONG_ADMIN_LISTEN
#     value: "0.0.0.0:8001"
_K8S_NAME = re.compile(
    r"""(?i)\bname\s*:\s*['"]?(KONG_ADMIN_LISTEN|KONG_ADMIN_GUI_LISTEN)['"]?\s*$"""
)
_K8S_VALUE = re.compile(
    r"""(?i)\bvalue\s*:\s*['"]?([^'"\n]+?)['"]?\s*$"""
)

_COMMENT_LINE = re.compile(r"""^\s*#""")

# IPv4 dotted-quad
_IPV4 = re.compile(r"""\b(\d{1,3}(?:\.\d{1,3}){3})\b""")
# bare port at start of value (no host)
_BARE_PORT = re.compile(r"""^\s*(\d{2,5})\b""")
# bracketed IPv6
_IPV6_ANY = re.compile(r"""\[\s*::\s*\]""")
_IPV6_LOOP = re.compile(r"""\[\s*::1\s*\]""")


def _is_loopback_v4(ip: str) -> bool:
    return ip.startswith("127.")


def _value_is_public(val: str) -> bool:
    """
    Decide whether an admin_listen value binds to a public iface.
    Accepts comma-separated multi-listen forms (e.g. "0.0.0.0:8001,
    127.0.0.1:8444 ssl"); returns True if ANY entry is public.
    """
    val = val.strip()
    if not val:
        return False
    if val.lower() in ("off", "none", "disabled"):
        return False

    parts = [p.strip() for p in val.split(",") if p.strip()]
    for part in parts:
        # Strip trailing listen attributes (ssl, http2, reuseport...)
        first = part.split()[0]

        if _IPV6_LOOP.search(first):
            continue
        if _IPV6_ANY.search(first):
            return True

        m = _IPV4.search(first)
        if m:
            ip = m.group(1)
            if _is_loopback_v4(ip):
                continue
            return True

        # No IP found — could be bare port "8001" or "localhost:8001".
        low = first.lower()
        if low.startswith("localhost"):
            continue
        if _BARE_PORT.match(first):
            return True
        # hostname:port — treat hostname as public unless localhost.
        if ":" in first:
            host = first.rsplit(":", 1)[0]
            if host.lower() not in ("localhost", "127.0.0.1", "[::1]"):
                return True
    return False


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


def scan_text(text: str, path: str) -> List[str]:
    findings: List[str] = []
    lines = text.splitlines()

    for lineno, raw in enumerate(lines, start=1):
        if _COMMENT_LINE.match(raw):
            continue
        line = _strip_inline_comment(raw)

        m = _KEY_LINE.match(line)
        if m:
            key = m.group(1)
            val = m.group("val")
            if _value_is_public(val):
                findings.append(
                    f"{path}:{lineno}: {key} = {val.strip()!r} binds "
                    f"the Kong Admin API to a non-loopback address; "
                    f"the Admin API is unauthenticated and must never "
                    f"be publicly exposed (CWE-306/CWE-668): "
                    f"{raw.strip()[:160]}"
                )
            continue

        # k8s env list pair
        nm = _K8S_NAME.search(line)
        if nm:
            key = nm.group(1)
            for j in range(lineno, min(lineno + 3, len(lines))):
                nxt = lines[j]
                vm = _K8S_VALUE.search(nxt)
                if vm:
                    if _value_is_public(vm.group(1)):
                        findings.append(
                            f"{path}:{lineno}: {key} (k8s env list) "
                            f"value {vm.group(1)!r} binds the Kong "
                            f"Admin API to a non-loopback address "
                            f"(CWE-306/CWE-668): {raw.strip()[:160]}"
                        )
                    break

    return findings


_TARGET_NAMES = (
    "dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
    "kong.conf",
    "kong.conf.default",
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
