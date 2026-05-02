#!/usr/bin/env python3
"""Detect snmpd configs (and compose env bundles) that ship the
well-known SNMPv1/v2c community strings ``public`` / ``private``
on a non-loopback listener.

SNMPv1 and SNMPv2c send the community string in clear UDP. The
defaults — ``public`` (read-only) and ``private`` (read-write) — are
the first thing every internet scanner tries. A reachable snmpd
with ``rocommunity public`` leaks the full MIB; with
``rwcommunity private`` an attacker can rewrite config on devices
that honour SNMP writes.

What's flagged
--------------
Per file (line-level):

* ``rocommunity public`` / ``rocommunity6 public``
* ``rwcommunity private`` / ``rwcommunity6 private``
* ``rocommunity public <source>`` where ``<source>`` is
  ``default``, ``0.0.0.0/0``, ``::/0``, or any non-loopback CIDR.
* ``com2sec <name> default public`` (older Net-SNMP form).
* ``community public`` (vendor-style line).
* Env-var assignments ``SNMP_COMMUNITY=public`` /
  ``SNMPD_COMMUNITY=public`` / ``SNMP_RO_COMMUNITY=public`` /
  ``SNMP_RW_COMMUNITY=private`` (compose / .env shape, quoted or
  unquoted).

Per file (whole-file):

* The file is an ``snmpd.conf`` AND has an ``agentaddress``
  directive bound to a non-loopback address AND has no
  ``createUser`` / ``usmUser`` / ``rouser`` / ``rwuser``
  directive (i.e., no SNMPv3 user defined).

What's NOT flagged
------------------
* ``rocommunity public 127.0.0.1`` / ``::1`` / ``localhost``.
* ``rouser monitor authPriv`` — SNMPv3 with auth+priv.
* Lines with a trailing ``# snmp-pub-ok`` comment.
* Files containing ``# snmp-pub-ok-file`` anywhere.
* Blocks bracketed by ``# snmp-pub-ok-begin`` /
  ``# snmp-pub-ok-end``.

Refs
----
* CWE-521: Weak Password Requirements
* CWE-798: Use of Hard-coded Credentials
* CWE-1188: Insecure Default Initialization of Resource
* US-CERT TA17-156A: SNMP default community strings

Usage
-----
    python3 detector.py <file_or_dir> [...]

Exit code: number of files with at least one finding (capped at 255).
Stdout:    ``<file>:<line>:<reason>``.
"""
from __future__ import annotations

import ipaddress
import re
import sys
from pathlib import Path
from typing import Iterable, List, Tuple

SUPPRESS_LINE = re.compile(r"#\s*snmp-pub-ok\b")
SUPPRESS_FILE = re.compile(r"#\s*snmp-pub-ok-file\b")
SUPPRESS_BEGIN = re.compile(r"#\s*snmp-pub-ok-begin\b")
SUPPRESS_END = re.compile(r"#\s*snmp-pub-ok-end\b")

# rocommunity / rwcommunity (and v6 variants) with public/private.
RO_COMMUNITY = re.compile(
    r"^\s*(rocommunity6?|rwcommunity6?)\s+(\S+)(?:\s+(\S+))?",
    re.IGNORECASE,
)
COM2SEC = re.compile(
    r"^\s*com2sec6?\s+\S+\s+(\S+)\s+(\S+)\b",
    re.IGNORECASE,
)
COMMUNITY_GENERIC = re.compile(
    r"^\s*community\s+(public|private)\b",
    re.IGNORECASE,
)
AGENTADDRESS = re.compile(
    r"^\s*agentaddress\s+(.+)$",
    re.IGNORECASE,
)
SNMPV3_USER = re.compile(
    r"^\s*(createUser|usmUser|rouser|rwuser)\b",
    re.IGNORECASE,
)
ENV_COMMUNITY = re.compile(
    r"\b(SNMP|SNMPD|SNMP_RO|SNMP_RW)_COMMUNITY\s*[:=]\s*[\"']?(public|private)[\"']?\b",
    re.IGNORECASE,
)

WEAK_COMMUNITIES = {"public", "private"}
LOOPBACK_LITERALS = {"127.0.0.1", "::1", "localhost", "default"}


def _strip_comment(line: str) -> str:
    return line.split("#", 1)[0]


def _source_is_public(source: str) -> bool:
    """Return True if a Net-SNMP source token is non-loopback."""
    s = source.strip().lower()
    if s == "default":
        # 'default' means *any* — public.
        return True
    if s in {"localhost", "127.0.0.1", "::1"}:
        return False
    # Try CIDR / IP parse.
    try:
        net = ipaddress.ip_network(s, strict=False)
        if net.is_loopback:
            return False
        return True
    except ValueError:
        # Hostname or unparseable — treat as public to be safe-ish, but
        # only if it doesn't look like loopback.
        return s not in LOOPBACK_LITERALS


def _agentaddress_is_public(spec: str) -> bool:
    """`agentaddress` can be like `udp:0.0.0.0:161,udp6:[::]:161` or
    just `161` (= all interfaces). Return True if any listener is
    non-loopback."""
    s = spec.strip()
    if not s:
        return False
    parts = [p.strip() for p in s.split(",") if p.strip()]
    if not parts:
        return False
    for p in parts:
        # Strip protocol prefix.
        body = p
        for proto in ("udp:", "udp6:", "tcp:", "tcp6:"):
            if body.lower().startswith(proto):
                body = body[len(proto):]
                break
        # If purely a port number, that's all-interfaces.
        if body.isdigit():
            return True
        # Pull host portion.
        if body.startswith("["):
            # ipv6 [::]:161
            close = body.find("]")
            if close == -1:
                continue
            host = body[1:close]
        else:
            host = body.split(":", 1)[0]
        h = host.lower()
        if h in {"127.0.0.1", "::1", "localhost"}:
            continue
        return True
    return False


def scan(source: str, filename: str = "") -> List[Tuple[int, str]]:
    findings: List[Tuple[int, str]] = []
    if SUPPRESS_FILE.search(source):
        return findings

    lines = source.splitlines()

    suppressed = set()
    in_fence = False
    for i, raw in enumerate(lines, start=1):
        if SUPPRESS_BEGIN.search(raw):
            in_fence = True
            suppressed.add(i)
            continue
        if SUPPRESS_END.search(raw):
            in_fence = False
            suppressed.add(i)
            continue
        if in_fence:
            suppressed.add(i)

    has_v3_user = False
    has_public_agentaddress = False

    for i, raw in enumerate(lines, start=1):
        if i in suppressed or SUPPRESS_LINE.search(raw):
            continue
        body = _strip_comment(raw)

        m = RO_COMMUNITY.match(body)
        if m:
            directive = m.group(1).lower()
            community = m.group(2)
            src = m.group(3) or "default"
            if community.lower() in WEAK_COMMUNITIES:
                if _source_is_public(src):
                    findings.append((
                        i,
                        f"{directive} {community} from non-loopback source '{src}' exposes default SNMP community",
                    ))
                # else loopback-only — skip
            continue

        m = COM2SEC.match(body)
        if m:
            src = m.group(1)
            community = m.group(2)
            if community.lower() in WEAK_COMMUNITIES and _source_is_public(src):
                findings.append((
                    i,
                    f"com2sec source '{src}' community '{community}' uses default SNMP community",
                ))
            continue

        m = COMMUNITY_GENERIC.match(body)
        if m:
            findings.append((
                i,
                f"community {m.group(1)} uses default SNMP community string",
            ))
            continue

        m = AGENTADDRESS.match(body)
        if m and _agentaddress_is_public(m.group(1)):
            has_public_agentaddress = True

        if SNMPV3_USER.match(body):
            has_v3_user = True

        env = ENV_COMMUNITY.search(raw)
        if env:
            findings.append((
                i,
                f"{env.group(1)}_COMMUNITY env var set to default '{env.group(2)}'",
            ))
            continue

    base = Path(filename).name.lower()
    if base in ("snmpd.conf",) and has_public_agentaddress and not has_v3_user:
        # Avoid double-counting if any rocommunity already flagged.
        if not any("rocommunity" in r or "rwcommunity" in r or "com2sec" in r for _, r in findings):
            findings.append((
                0,
                "snmpd.conf has non-loopback agentaddress and no SNMPv3 user (createUser/rouser/rwuser)",
            ))

    return findings


def _iter_files(path: Path) -> Iterable[Path]:
    if path.is_file():
        yield path
        return
    seen = set()
    patterns = (
        "snmpd.conf",
        "*.snmpd.conf",
        "snmp.conf",
        "docker-compose*.y*ml",
        ".env",
        "*.env",
    )
    for pattern in patterns:
        for sub in sorted(path.rglob(pattern)):
            if sub.is_file() and sub not in seen:
                seen.add(sub)
                yield sub


def scan_paths(paths: Iterable[Path]) -> int:
    bad_files = 0
    for root in paths:
        for f in _iter_files(root):
            try:
                source = f.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as exc:
                print(f"{f}:0:read-error: {exc}")
                continue
            hits = scan(source, str(f))
            if hits:
                bad_files += 1
                for line, reason in hits:
                    print(f"{f}:{line}:{reason}")
    return bad_files


def main(argv: List[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 0
    paths = [Path(a) for a in argv[1:]]
    return min(255, scan_paths(paths))


if __name__ == "__main__":
    sys.exit(main(sys.argv))
