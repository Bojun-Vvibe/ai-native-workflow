#!/usr/bin/env python3
"""Detect Apache HBase ``hbase-site.xml`` configurations that ship with
``hbase.security.authentication`` set to the default ``simple`` value
on a cluster whose RPC port is not loopback-only.

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

SUPPRESS = re.compile(r"<!--\s*hbase-auth-allowed\s*-->")

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

    auth = props.get("hbase.security.authentication", "").lower()
    authz = props.get("hbase.security.authorization", "").lower()
    rpc_protection = props.get("hbase.rpc.protection", "").lower()
    master_bind = props.get("hbase.master.ipc.address", "")
    rs_bind = props.get("hbase.regionserver.ipc.address", "")
    zk_quorum = props.get("hbase.zookeeper.quorum", "")
    cluster_distributed = props.get("hbase.cluster.distributed", "false").lower()

    # Only flag when explicitly set to simple (the insecure default).
    # Missing value is not flagged: many real configs inherit from
    # hbase-default.xml and the operator may layer kerberos elsewhere.
    if auth != "simple":
        return findings

    # Loopback-only deployments are out of scope.
    binds = [b for b in (master_bind, rs_bind) if b]
    if binds and all(b in LOOPBACK_HOSTS for b in binds):
        return findings

    # Single-node, non-distributed, with a loopback ZK quorum is also
    # treated as a dev sandbox.
    if (
        cluster_distributed == "false"
        and zk_quorum
        and all(host.strip() in LOOPBACK_HOSTS for host in zk_quorum.split(","))
    ):
        return findings

    line = _line_of(source, "hbase.security.authentication")
    reasons = ["hbase.security.authentication=simple (no Kerberos / SASL auth)"]
    if authz != "true":
        reasons.append("hbase.security.authorization is not true (no ACL)")
    if rpc_protection in ("", "authentication"):
        reasons.append(
            f"hbase.rpc.protection={rpc_protection or '<unset>'} "
            "(no integrity/privacy on the wire)"
        )
    findings.append((line, "; ".join(reasons)))
    return findings


def scan_paths(paths: Iterable[Path]) -> int:
    bad_files = 0
    targets: List[Path] = []
    for path in paths:
        if path.is_dir():
            for ext in ("hbase-site.xml", "*.hbase-site.xml"):
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
