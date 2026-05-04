#!/usr/bin/env python3
"""Detect Apache Spark ``spark-defaults.conf`` files that ship
``spark.authenticate=false`` (the upstream default) on a deployment
whose RPC surface is reachable beyond loopback.

See README.md for the precise rules. Exit code is the count of files
with at least one finding (capped at 255). Stdout lines have the form
``<file>:<line>:<reason>``.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Tuple
from urllib.parse import urlparse

SUPPRESS = re.compile(r"^\s*#\s*spark-auth-allowed\s*$", re.MULTILINE)
LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost", "0:0:0:0:0:0:0:1"}

BIND_HOST_KEYS = (
    "spark.driver.host",
    "spark.driver.bindAddress",
    "spark.blockManager.host",
    "spark.ui.host",
)


def _line_of(source: str, needle: str) -> int:
    for i, raw in enumerate(source.splitlines(), 1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        parts = line.split(None, 1)
        if parts and parts[0] == needle:
            return i
    return 1


def _parse_props(source: str) -> Dict[str, str]:
    props: Dict[str, str] = {}
    for raw in source.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        # `key value` or `key = value`
        if "=" in line and (
            "\t" not in line.split("=", 1)[0]
            and " " not in line.split("=", 1)[0].strip()
        ):
            k, v = line.split("=", 1)
            props[k.strip()] = v.strip()
            continue
        parts = line.split(None, 1)
        if len(parts) == 2:
            props[parts[0].strip()] = parts[1].strip()
        elif len(parts) == 1:
            props[parts[0].strip()] = ""
    return props


def _master_is_remote(master: str) -> Tuple[bool, str]:
    """Return (is_remote, host_description)."""
    m = master.strip()
    if not m:
        return False, ""
    low = m.lower()
    if low == "local" or low.startswith("local["):
        return False, "local"
    if low.startswith("spark://"):
        # spark://host:port[,host:port...]
        rest = m[len("spark://"):]
        first = rest.split(",", 1)[0]
        host = first.rsplit(":", 1)[0] if ":" in first else first
        if host in LOOPBACK_HOSTS:
            return False, host
        return True, host or "<unknown>"
    if low.startswith("k8s://") or low.startswith("mesos://"):
        try:
            host = urlparse(m).hostname or ""
        except ValueError:
            host = ""
        if host and host in LOOPBACK_HOSTS:
            return False, host
        return True, host or low.split("://", 1)[0]
    if low in {"yarn", "yarn-client", "yarn-cluster"}:
        return True, "yarn"
    return True, m


def scan(source: str) -> List[Tuple[int, str]]:
    findings: List[Tuple[int, str]] = []
    if SUPPRESS.search(source):
        return findings

    props = _parse_props(source)

    auth_raw = props.get("spark.authenticate", "false").strip().lower()
    if auth_raw == "true":
        # If a non-empty secret is also configured we trust the operator.
        secret = props.get("spark.authenticate.secret", "").strip()
        if secret:
            return findings
        # authenticate=true with empty secret is itself broken; fall through.
        line = _line_of(source, "spark.authenticate")
        findings.append(
            (
                line,
                "spark.authenticate=true but spark.authenticate.secret is empty"
                " — RPC handshake will fail open in older Spark releases",
            )
        )
        return findings

    master = props.get("spark.master", "")
    remote, host_desc = _master_is_remote(master)
    if not remote:
        # Check explicit non-loopback bind hosts as a fallback signal.
        for k in BIND_HOST_KEYS:
            v = props.get(k, "").strip()
            if v and v not in LOOPBACK_HOSTS and v not in {"", "0.0.0.0", "::"}:
                remote = True
                host_desc = f"{k}={v}"
                break
            if v in {"0.0.0.0", "::"}:
                remote = True
                host_desc = f"{k}={v}"
                break
        if not remote:
            return findings

    needle = (
        "spark.authenticate" if "spark.authenticate" in props else "spark.master"
    )
    line = _line_of(source, needle)
    auth_state = "unset" if "spark.authenticate" not in props else "false"
    reasons = [
        f"spark.authenticate is {auth_state} (master/host={host_desc}) — "
        f"any peer reaching the RPC port can register as an executor"
    ]
    crypto = props.get("spark.network.crypto.enabled", "false").strip().lower()
    if crypto != "true":
        reasons.append(
            "spark.network.crypto.enabled is not true — RPC payloads are "
            "transmitted in cleartext"
        )
    ui_acls = props.get("spark.ui.acls.enable", "false").strip().lower()
    if ui_acls != "true":
        reasons.append(
            "spark.ui.acls.enable is not true — Spark UI accepts kill/stage "
            "requests from any caller"
        )
    if "spark.authenticate.secret" in props and not props[
        "spark.authenticate.secret"
    ].strip():
        reasons.append("spark.authenticate.secret is present but empty")
    findings.append((line, "; ".join(reasons)))
    return findings


def scan_paths(paths: Iterable[Path]) -> int:
    bad_files = 0
    targets: List[Path] = []
    for path in paths:
        if path.is_dir():
            targets.extend(sorted(path.rglob("spark-defaults.conf")))
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
