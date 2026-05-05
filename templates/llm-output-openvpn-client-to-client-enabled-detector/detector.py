#!/usr/bin/env python3
"""Detect OpenVPN server configs that enable ``client-to-client``
forwarding, especially when paired with ``duplicate-cn`` or no TLS
client-cert verification.

Background
----------
OpenVPN's ``client-to-client`` directive bypasses the kernel's
forwarding table and relays packets between connected VPN clients
inside the OpenVPN process itself. Two consequences:

1. iptables / nftables FORWARD rules on the VPN host do **not** see
   intra-tunnel traffic, so site-perimeter ACLs that "block lateral
   movement between VPN users" silently do nothing.
2. Combined with ``duplicate-cn`` (allow more than one client to
   present the same certificate Common Name) you have effectively a
   shared-credential mesh: any one stolen client cert lets an attacker
   join the tunnel and reach every other connected user as if they
   were on the same L2 segment.

Both are widely-emitted LLM defaults because the canonical
"site-to-site OpenVPN" tutorial enables ``client-to-client`` so a
roaming road-warrior config "just works", and ``duplicate-cn`` is
suggested as a quick fix when "the cert keeps disconnecting the old
session". Neither belongs in a multi-tenant deployment.

What's checked (per file)
-------------------------
The detector flags a file iff it parses as an OpenVPN server-side
config (has at least one of ``server``, ``server-bridge``, ``mode
server``, ``port`` + ``proto``, ``tls-server``, ``dev tun``/``dev
tap``) AND any of:

* ``client-to-client`` directive uncommented at column-0 (OpenVPN
  ignores leading whitespace, so we strip it).
* ``duplicate-cn`` uncommented (this alone is high-risk: it disables
  the "one connection per cert" guarantee).
* ``client-to-client`` AND ``verify-client-cert none`` together —
  intra-tunnel forwarding without per-client cert auth.

Lines starting with ``#`` or ``;`` (OpenVPN's two comment characters)
are stripped. Trailing ``# ...`` / ``; ...`` comments on the same line
are also stripped before the directive match so a comment cannot
shield a directive on the same line.

Suppress per file with ``# openvpn-c2c-allowed`` anywhere in the file
(useful for closed lab nets, single-tenant overlays).

CWE refs
~~~~~~~~
* CWE-668: Exposure of Resource to Wrong Sphere
* CWE-284: Improper Access Control
* CWE-306: Missing Authentication for Critical Function (when paired
  with ``verify-client-cert none``)

Usage
-----
    python3 detector.py <path> [<path> ...]

Exit code: number of files with at least one finding (capped at 255).
Stdout:    ``<file>:<line>:<reason>``.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Iterable, List, Tuple

SUPPRESS = re.compile(r"#\s*openvpn-c2c-allowed", re.IGNORECASE)

# OpenVPN treats `;` and `#` as comment markers. Strip them.
_COMMENT_RE = re.compile(r"\s+[#;].*$")
_FULL_COMMENT_RE = re.compile(r"^\s*[#;]")

# Server-shape markers — at least one must be present for the file to
# count as an OpenVPN server config.
SERVER_MARKERS = (
    re.compile(r"^\s*server\s+\d", re.IGNORECASE),
    re.compile(r"^\s*server-bridge\b", re.IGNORECASE),
    re.compile(r"^\s*mode\s+server\b", re.IGNORECASE),
    re.compile(r"^\s*tls-server\b", re.IGNORECASE),
    re.compile(r"^\s*push\s+\"", re.IGNORECASE),
    re.compile(r"^\s*ifconfig-pool\b", re.IGNORECASE),
    re.compile(r"^\s*client-config-dir\b", re.IGNORECASE),
)

# Directives we flag.
C2C_RE = re.compile(r"^\s*client-to-client\b", re.IGNORECASE)
DUP_CN_RE = re.compile(r"^\s*duplicate-cn\b", re.IGNORECASE)
VERIFY_NONE_RE = re.compile(
    r"^\s*verify-client-cert\s+none\b", re.IGNORECASE
)
# `client-cert-not-required` is the legacy spelling (deprecated in
# OpenVPN 2.5, removed in 2.6, but still emitted by old templates).
CCNR_RE = re.compile(r"^\s*client-cert-not-required\b", re.IGNORECASE)


def _strip(line: str) -> str:
    if _FULL_COMMENT_RE.match(line):
        return ""
    return _COMMENT_RE.sub("", line)


def _is_server_config(stripped_lines: List[str]) -> bool:
    return any(
        any(rx.match(s) for rx in SERVER_MARKERS) for s in stripped_lines
    )


def scan(source: str) -> List[Tuple[int, str]]:
    findings: List[Tuple[int, str]] = []
    if SUPPRESS.search(source):
        return findings

    raw_lines = source.splitlines()
    stripped = [_strip(l) for l in raw_lines]

    if not _is_server_config(stripped):
        return findings

    c2c_line = 0
    dup_cn_line = 0
    verify_none_line = 0
    ccnr_line = 0

    for idx, s in enumerate(stripped, start=1):
        if not s.strip():
            continue
        if c2c_line == 0 and C2C_RE.match(s):
            c2c_line = idx
        if dup_cn_line == 0 and DUP_CN_RE.match(s):
            dup_cn_line = idx
        if verify_none_line == 0 and VERIFY_NONE_RE.match(s):
            verify_none_line = idx
        if ccnr_line == 0 and CCNR_RE.match(s):
            ccnr_line = idx

    if c2c_line and (verify_none_line or ccnr_line):
        cause = (
            f"verify-client-cert none (line {verify_none_line})"
            if verify_none_line
            else f"client-cert-not-required (line {ccnr_line})"
        )
        findings.append(
            (
                c2c_line,
                f"client-to-client enabled WITH {cause} — intra-tunnel "
                "forwarding without per-client cert auth",
            )
        )
    elif c2c_line:
        findings.append(
            (
                c2c_line,
                "client-to-client enabled — intra-tunnel packets bypass "
                "kernel FORWARD chain, defeating perimeter ACLs between "
                "VPN clients",
            )
        )

    if dup_cn_line:
        findings.append(
            (
                dup_cn_line,
                "duplicate-cn enabled — multiple clients may present the "
                "same Common Name; one stolen cert grants shared mesh "
                "access",
            )
        )

    return findings


def scan_paths(paths: Iterable[Path]) -> int:
    bad_files = 0
    targets: List[Path] = []
    for path in paths:
        if path.is_dir():
            for ext in ("*.conf", "*.ovpn"):
                targets.extend(sorted(path.rglob(ext)))
        else:
            targets.append(path)
    for f in targets:
        try:
            source = f.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            print(f"{f}:0:read-error: {exc}")
            continue
        hits = scan(source)
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
