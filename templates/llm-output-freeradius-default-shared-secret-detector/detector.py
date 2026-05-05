#!/usr/bin/env python3
"""Detect FreeRADIUS / RADIUS-shape configs (and compose env bundles)
that ship a default / well-known shared secret on a NAS or proxy
``client {}`` block reachable from non-loopback peers.

The RADIUS protocol authenticates a NAS to the RADIUS server using
a single per-client shared secret. The secret is also used to obscure
the User-Password attribute (RFC 2865) and to compute the Response
Authenticator. A weak secret therefore both allows an attacker who
can spoof a NAS source address to issue arbitrary Access-Request /
Accounting-Request packets, and lets a passive observer recover
user passwords offline. The defaults shipped in vendor docs and
tutorials -- ``testing123``, ``secret``, ``radius``, ``changeme``,
``password`` -- are the first thing scanners try.

What's flagged
--------------
Per file (line-level):

* ``secret = testing123`` / ``secret=testing123`` (and the other
  well-known defaults below) inside any ``client {}`` block, or at
  the top level of an ``clients.conf``-shaped file.
* ``secret = "<weak>"`` with quoted form.
* The same on ``home_server {}`` (proxy) blocks.
* Env-var assignments shipped in compose / .env shape:
  ``RADIUS_SECRET=<weak>``, ``FREERADIUS_SECRET=<weak>``,
  ``RADIUS_CLIENT_SECRET=<weak>``, ``RADSEC_SECRET=<weak>``.

Per file (whole-file):

* The file is a ``clients.conf`` AND has a ``client { ... }`` block
  whose ``ipaddr`` / ``ipv4addr`` / ``ipv6addr`` is non-loopback
  AND no ``secret`` line at all (FreeRADIUS treats absent ``secret``
  in a NAS block as a fatal startup error -- but we still flag the
  shape because LLMs emit it and humans paste in a default).

What's NOT flagged
------------------
* ``secret = ...`` where the value is >= 22 chars and contains at
  least one digit and at least one non-alphanumeric (a reasonable
  proxy for "not a default tutorial value").
* ``client localhost { ipaddr = 127.0.0.1; secret = testing123 }``
  -- loopback-only blocks are noisy but not exploitable from the
  network.
* Lines with a trailing ``# radius-default-ok`` comment.
* Files containing ``# radius-default-ok-file`` anywhere.
* Blocks bracketed by ``# radius-default-ok-begin`` /
  ``# radius-default-ok-end``.

Refs
----
* CWE-521: Weak Password Requirements
* CWE-798: Use of Hard-coded Credentials
* CWE-1188: Insecure Default Initialization of Resource
* RFC 2865 s.3 -- shared secret usage and recommendations

Usage
-----
    python3 detector.py <file_or_dir> [...]

Exit code: number of files with at least one finding (capped at 255).
Stdout:    ``<file>:<line>:<reason>``.
"""
from __future__ import annotations

import ipaddress
import os
import re
import sys
from typing import Iterable, List, Tuple

WEAK_SECRETS = {
    "testing123",
    "testing",
    "secret",
    "radius",
    "freeradius",
    "changeme",
    "change-me",
    "password",
    "passw0rd",
    "admin",
    "default",
    "shared",
    "shared-secret",
    "sharedsecret",
    "demo",
    "example",
    "test",
    "1234",
    "12345",
    "123456",
}

ENV_KEYS = (
    "RADIUS_SECRET",
    "RADIUSD_SECRET",
    "FREERADIUS_SECRET",
    "RADIUS_CLIENT_SECRET",
    "RADIUS_SHARED_SECRET",
    "RADSEC_SECRET",
)

ENV_RE = re.compile(
    r"^\s*(?:export\s+)?(" + "|".join(ENV_KEYS) + r")\s*[:=]\s*(.+?)\s*$"
)

# secret = <value>   |   secret="<value>"   |   secret = '<value>'
SECRET_LINE_RE = re.compile(
    r"""^\s*secret\s*=\s*(?P<val>"[^"]*"|'[^']*'|[^\s#]+)\s*(?:\#.*)?$"""
)

IPADDR_LINE_RE = re.compile(
    r"^\s*(?:ipaddr|ipv4addr|ipv6addr|ipv4netmask)\s*=\s*([^\s#]+)"
)

CLIENT_OPEN_RE = re.compile(r"^\s*client\s+\S+\s*\{\s*$|^\s*client\s+\S+\s*$")
HOME_SERVER_OPEN_RE = re.compile(r"^\s*home_server\s+\S+\s*\{\s*$")
BLOCK_OPEN_RE = re.compile(r"\{\s*$")
BLOCK_CLOSE_RE = re.compile(r"^\s*\}")

OK_LINE = "# radius-default-ok"
OK_FILE = "# radius-default-ok-file"
OK_BEGIN = "# radius-default-ok-begin"
OK_END = "# radius-default-ok-end"


def _strip_quotes(v: str) -> str:
    if len(v) >= 2 and v[0] == v[-1] and v[0] in ("'", '"'):
        return v[1:-1]
    return v


def _is_weak_secret(value: str) -> bool:
    v = _strip_quotes(value).strip()
    if not v:
        return True  # empty secret is the worst case
    low = v.lower()
    if low in WEAK_SECRETS:
        return True
    # Heuristic: short + alnum-only is a default-ish secret.
    if len(v) < 12 and re.fullmatch(r"[A-Za-z0-9]+", v):
        return True
    # Reasonable strength gate -- 22+ chars with digit+symbol passes.
    if len(v) >= 22 and any(c.isdigit() for c in v) and any(
        not c.isalnum() for c in v
    ):
        return False
    # Medium length but alphanum-only -> still suspicious.
    if re.fullmatch(r"[A-Za-z0-9]+", v) and len(v) < 22:
        return True
    return False


def _is_loopback(addr: str) -> bool:
    a = addr.strip().strip('"').strip("'").rstrip(";").strip()
    if a in {"localhost", "127.0.0.1", "::1"}:
        return True
    try:
        ip = ipaddress.ip_address(a)
        return ip.is_loopback
    except ValueError:
        try:
            net = ipaddress.ip_network(a, strict=False)
            return net.is_loopback
        except ValueError:
            return False


def _looks_like_clients_conf(path: str, text: str) -> bool:
    base = os.path.basename(path).lower()
    if base in {"clients.conf", "radiusd.conf", "proxy.conf"}:
        return True
    return bool(re.search(r"^\s*client\s+\S+\s*\{", text, re.MULTILINE))


def _walk(paths: Iterable[str]) -> Iterable[str]:
    for p in paths:
        if os.path.isdir(p):
            for root, _, files in os.walk(p):
                for f in files:
                    yield os.path.join(root, f)
        else:
            yield p


def _scan_file(path: str) -> List[Tuple[int, str]]:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            text = fh.read()
    except OSError:
        return []

    if OK_FILE in text:
        return []

    findings: List[Tuple[int, str]] = []
    lines = text.splitlines()

    # Skip-window handling for ok-begin / ok-end.
    skip = False
    block_stack: List[dict] = []  # each: {"type":..., "ipaddr":..., "ipline":..., "has_secret":bool}
    is_clients_shape = _looks_like_clients_conf(path, text)
    is_env_shape = path.endswith(".env") or "compose" in os.path.basename(path).lower()

    for i, raw in enumerate(lines, 1):
        if OK_BEGIN in raw:
            skip = True
            continue
        if OK_END in raw:
            skip = False
            continue
        if skip:
            continue

        line = raw.split("#", 1)[0] if OK_LINE not in raw else raw
        # OK_LINE acts as a per-line allow.
        if OK_LINE in raw:
            # Still track block bookkeeping below, but never flag.
            allow_line = True
        else:
            allow_line = False

        # Track block scope for clients.conf-shape files.
        if CLIENT_OPEN_RE.match(raw):
            block_stack.append({"type": "client", "ipaddr": None, "ipline": i, "has_secret": False})
        elif HOME_SERVER_OPEN_RE.match(raw):
            block_stack.append({"type": "home_server", "ipaddr": None, "ipline": i, "has_secret": False})
        elif BLOCK_OPEN_RE.search(raw) and not block_stack:
            # generic open we don't care about
            pass

        m_ip = IPADDR_LINE_RE.match(raw)
        if m_ip and block_stack:
            block_stack[-1]["ipaddr"] = m_ip.group(1).rstrip(";").strip()

        # Per-line: env-shape RADIUS_SECRET=...
        m_env = ENV_RE.match(raw)
        if m_env and not allow_line:
            key = m_env.group(1)
            val = m_env.group(2).strip().strip('"').strip("'")
            if _is_weak_secret(val):
                findings.append((i, f"weak RADIUS shared secret in env var {key}={val!r}"))

        # Per-line: secret = ...
        m_sec = SECRET_LINE_RE.match(line if not allow_line else raw.split("#", 1)[0])
        if m_sec:
            val = m_sec.group("val")
            inside_loopback_block = False
            if block_stack:
                block_stack[-1]["has_secret"] = True
                ip = block_stack[-1]["ipaddr"]
                if ip and _is_loopback(ip):
                    inside_loopback_block = True
            if not allow_line and not inside_loopback_block and _is_weak_secret(val):
                findings.append(
                    (i, f"weak RADIUS shared secret value {val!r}")
                )

        # Close block.
        if BLOCK_CLOSE_RE.match(raw) and block_stack:
            blk = block_stack.pop()
            if (
                is_clients_shape
                and blk["type"] == "client"
                and blk["ipaddr"]
                and not _is_loopback(blk["ipaddr"])
                and not blk["has_secret"]
            ):
                findings.append(
                    (blk["ipline"], "client {} block on non-loopback NAS has no secret directive")
                )

    return findings


def main(argv: List[str]) -> int:
    if len(argv) < 2:
        print(f"usage: {argv[0]} <file_or_dir> [...]", file=sys.stderr)
        return 2

    flagged_files = 0
    for path in _walk(argv[1:]):
        # Skip obvious binary noise.
        if path.endswith((".png", ".jpg", ".gz", ".tar", ".zip")):
            continue
        findings = _scan_file(path)
        if findings:
            flagged_files += 1
            for ln, reason in findings:
                print(f"{path}:{ln}:{reason}")
    return min(flagged_files, 255)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
