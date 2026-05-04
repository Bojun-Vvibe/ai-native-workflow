#!/usr/bin/env python3
"""Detect Apache Hive ``hive-site.xml`` configurations that ship
HiveServer2 with ``hive.server2.authentication = NONE`` while bound to
a non-loopback host.

See README.md for the precise rules. Exit code is the count of files
with at least one finding (capped at 255). Stdout lines have the form
``<file>:<line>:<reason>``.
"""
from __future__ import annotations

import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Iterable, List, Tuple

SUPPRESS = re.compile(r"<!--\s*hive-auth-allowed\s*-->")

LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost", "0:0:0:0:0:0:0:1"}


def _line_of(source: str, needle: str) -> int:
    idx = source.find(needle)
    if idx < 0:
        return 1
    return source.count("\n", 0, idx) + 1


def _props(root: ET.Element) -> dict:
    out = {}
    for prop in root.findall("property"):
        name_el = prop.find("name")
        val_el = prop.find("value")
        if name_el is None or val_el is None:
            continue
        name = (name_el.text or "").strip()
        val = (val_el.text or "").strip()
        if name:
            out[name] = val
    return out


def scan(source: str) -> List[Tuple[int, str]]:
    findings: List[Tuple[int, str]] = []
    if SUPPRESS.search(source):
        return findings
    try:
        root = ET.fromstring(source)
    except ET.ParseError:
        return findings
    if root.tag != "configuration":
        return findings

    props = _props(root)

    auth_raw = props.get("hive.server2.authentication", "")
    auth = auth_raw.upper()
    # Only flag when explicitly NONE (the documented insecure default
    # users most often paste from quickstart guides).
    if auth != "NONE":
        return findings

    host = props.get("hive.server2.thrift.bind.host", "").strip()
    http_path_set = "hive.server2.thrift.http.path" in props
    transport_mode = props.get("hive.server2.transport.mode", "binary").lower()

    # Loopback-only HS2 is treated as a dev sandbox.
    if host and host in LOOPBACK_HOSTS:
        return findings

    use_ssl = props.get("hive.server2.use.SSL", "false").lower() == "true"
    doas = props.get("hive.server2.enable.doAs", "true").lower() == "true"
    authz_mgr = props.get("hive.security.authorization.manager", "").strip()
    authz_enabled = (
        props.get("hive.security.authorization.enabled", "false").lower() == "true"
    )

    line = _line_of(source, "hive.server2.authentication")
    bind_desc = host if host else "<all interfaces>"
    transport_desc = (
        "http" if transport_mode == "http" or http_path_set else transport_mode
    )
    reasons = [
        f"hive.server2.authentication=NONE on {transport_desc} transport "
        f"bind={bind_desc} (anonymous JDBC/ODBC accepted)",
    ]
    if not use_ssl:
        reasons.append("hive.server2.use.SSL is not true (cleartext)")
    if doas:
        reasons.append(
            "hive.server2.enable.doAs=true with NONE auth — every query "
            "runs as the client-supplied user string"
        )
    if not authz_enabled or not authz_mgr:
        reasons.append(
            "hive.security.authorization is not enabled — no SQL-standard ACL"
        )
    findings.append((line, "; ".join(reasons)))
    return findings


def scan_paths(paths: Iterable[Path]) -> int:
    bad_files = 0
    targets: List[Path] = []
    for path in paths:
        if path.is_dir():
            for ext in ("hive-site.xml", "*.hive-site.xml"):
                targets.extend(sorted(path.rglob(ext)))
        else:
            targets.append(path)
    seen = set()
    for f in targets:
        if f in seen:
            continue
        seen.add(f)
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
