#!/usr/bin/env python3
"""Detect ``stunnel.conf`` services that run in server mode
(``client = no``) with peer-certificate verification turned off
(``verify = 0`` or no ``verify`` directive plus no ``CAfile`` /
``CApath``).

A server-mode stunnel that does not check client certs is, by
itself, just "TLS termination". The unsafe pattern flagged here is
the very common one in which the operator *wanted* mutual-TLS (they
are forwarding to a sensitive backend like a database admin port,
``redis``, ``etcd``, etc.) but copy-pasted ``verify = 0`` from a
quickstart and never noticed that every TCP client on the network
is now allowed in.

See README.md for the precise rules. Exit code is the count of files
with at least one finding (capped at 255). Stdout lines have the form
``<file>:<line>:<reason>``.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Iterable, List, Tuple

SUPPRESS = re.compile(r"[#;]\s*stunnel-verify-allowed\b")

SECTION_RE = re.compile(r"^\s*\[([^\]]+)\]\s*$")
KV_RE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_.-]*)\s*=\s*(.*?)\s*$")

# Backends that strongly imply the operator wanted mTLS in front of
# a sensitive service. Matched against the ``connect`` directive.
SENSITIVE_BACKENDS = (
    "6379",      # redis
    "5432",      # postgres
    "3306",      # mysql/mariadb
    "27017",     # mongo
    "2379",      # etcd client
    "2380",      # etcd peer
    "9200",      # elasticsearch http
    "9300",      # elasticsearch transport
    "8500",      # consul http
    "5984",      # couchdb
    "8086",      # influxdb
    "5672",      # amqp
    "15672",     # rabbitmq mgmt
    "8080",      # generic admin
    "8443",      # generic admin tls
    "9000",      # minio / portainer
    "9090",      # prometheus
    "5601",      # opensearch dashboards
)


def _strip_comment(value: str) -> str:
    for marker in ("#", ";"):
        idx = value.find(marker)
        if idx >= 0:
            value = value[:idx]
    return value.strip()


def _parse(source: str) -> Tuple[dict, dict]:
    """Return (globals, services) where each maps key->(value, line).

    services is a dict[name] -> dict[key] -> (value, line).
    Within stunnel, options before the first [section] are global.
    """
    globals_: dict = {}
    services: dict = {}
    section = None  # None = global
    for lineno, raw in enumerate(source.splitlines(), 1):
        line = raw.rstrip()
        if not line.strip() or line.lstrip().startswith((";", "#")):
            continue
        m = SECTION_RE.match(line)
        if m:
            section = m.group(1).strip()
            services.setdefault(section, {})
            continue
        kv = KV_RE.match(line)
        if not kv:
            continue
        key = kv.group(1).strip().lower()
        val = _strip_comment(kv.group(2))
        target = globals_ if section is None else services[section]
        target[key] = (val, lineno)
    return globals_, services


def _is_sensitive_connect(connect: str) -> bool:
    if not connect:
        return False
    c = connect.strip().lower()
    # connect = host:port or just :port
    port = c.rsplit(":", 1)[-1]
    return port in SENSITIVE_BACKENDS


def scan(source: str) -> List[Tuple[int, str]]:
    findings: List[Tuple[int, str]] = []
    if SUPPRESS.search(source):
        return findings

    globals_, services = _parse(source)
    if not services:
        return findings

    for name, kvs in services.items():
        client = kvs.get("client", ("no", 0))[0].strip().lower()
        # Only server-mode services are in scope. Default for stunnel
        # when ``client`` is unset is server mode.
        if client == "yes":
            continue

        connect = kvs.get("connect", ("", 0))[0]
        if not _is_sensitive_connect(connect):
            continue

        verify_val_line = kvs.get("verify") or globals_.get("verify")
        verify_str = (verify_val_line[0] if verify_val_line else "").strip()
        verify_line = verify_val_line[1] if verify_val_line else 0

        # verifyChain / verifyPeer (newer stunnel). Treat presence of
        # either set to "yes" as adequate.
        for k in ("verifychain", "verifypeer"):
            v = kvs.get(k) or globals_.get(k)
            if v and v[0].strip().lower() == "yes":
                # Adequately configured — skip this service.
                verify_str = "__ok__"
                break
        if verify_str == "__ok__":
            continue

        ca_file = (kvs.get("cafile") or globals_.get("cafile") or ("", 0))[0]
        ca_path = (kvs.get("capath") or globals_.get("capath") or ("", 0))[0]

        verify_explicit_zero = verify_str == "0"
        verify_missing = verify_str == ""

        # Flag if verify=0 OR (verify unset AND no CA configured).
        if not verify_explicit_zero:
            if not verify_missing:
                # verify is set to 1/2/3/4 — adequate.
                continue
            if ca_file or ca_path:
                # Verify defaults to 0 in older stunnel, but operator
                # configured a CA, which strongly implies they meant
                # to verify. Don't second-guess; skip.
                continue

        line = verify_line or kvs.get("connect", (None, 1))[1]
        reasons = []
        if verify_explicit_zero:
            reasons.append(
                f"[{name}] verify=0 with connect={connect} — server "
                "accepts every TCP client and forwards to a sensitive "
                "backend"
            )
        else:
            reasons.append(
                f"[{name}] no verify/CAfile/CApath with connect="
                f"{connect} — peer cert is never checked"
            )
        if not (ca_file or ca_path):
            reasons.append("CAfile and CApath are unset (no trust anchor)")
        findings.append((line, "; ".join(reasons)))
    return findings


def scan_paths(paths: Iterable[Path]) -> int:
    bad_files = 0
    targets: List[Path] = []
    for path in paths:
        if path.is_dir():
            for pattern in ("stunnel.conf", "*.stunnel.conf"):
                targets.extend(sorted(path.rglob(pattern)))
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
