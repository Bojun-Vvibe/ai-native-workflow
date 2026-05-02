#!/usr/bin/env python3
"""Detect PostgreSQL configs that expose ``listen_addresses`` on a
non-loopback interface while ``pg_hba.conf`` permits weak auth.

Inputs:
  - A path to a ``postgresql.conf`` (or ``*.postgresql.conf``).
  - Optionally, sibling ``pg_hba.conf`` files in the same directory
    are auto-discovered. Additional paths can be passed positionally.
  - A directory: scanned recursively for ``postgresql.conf`` /
    ``pg_hba.conf``.

Findings are reported as ``<file>:<line>:<reason>``. Exit code is the
count of files with at least one finding (capped at 255).

Suppression: any file containing ``# pg-public-allowed`` is skipped
(applies to both postgresql.conf and pg_hba.conf).

CWE refs: CWE-306, CWE-284, CWE-319.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Iterable, List, Tuple

SUPPRESS = re.compile(r"#\s*pg-public-allowed")

LISTEN_RE = re.compile(
    r"""^\s*listen_addresses\s*=\s*['"]?([^'"#\n]+?)['"]?\s*(?:\#.*)?$""",
    re.IGNORECASE,
)

LOOPBACK = {"localhost", "127.0.0.1", "::1"}

WEAK_AUTH = {"trust", "password"}
STRONG_AUTH = {
    "scram-sha-256",
    "md5",
    "cert",
    "gss",
    "sspi",
    "peer",
    "ident",
    "ldap",
    "radius",
    "pam",
    "bsd",
    "reject",
}

# CIDRs that are loopback-only.
LOOPBACK_CIDRS = {
    "127.0.0.1/32",
    "::1/128",
    "127.0.0.1",
    "::1",
}


def _addrs_are_loopback_only(value: str) -> bool:
    addrs = [a.strip() for a in value.split(",") if a.strip()]
    if not addrs:
        return True  # treat empty as default (localhost)
    return all(a in LOOPBACK for a in addrs)


def _is_exposed_address(value: str) -> bool:
    addrs = [a.strip() for a in value.split(",") if a.strip()]
    for a in addrs:
        if a == "*":
            return True
        if a == "0.0.0.0" or a == "::":
            return True
        if a not in LOOPBACK:
            return True
    return False


def scan_postgresql_conf(source: str) -> List[Tuple[int, str, str]]:
    """Returns list of (line, reason, listen_value)."""
    findings: List[Tuple[int, str, str]] = []
    if SUPPRESS.search(source):
        return findings
    for i, raw in enumerate(source.splitlines(), start=1):
        # Skip pure comment lines.
        if raw.lstrip().startswith("#"):
            continue
        m = LISTEN_RE.match(raw)
        if not m:
            continue
        value = m.group(1).strip()
        if _is_exposed_address(value):
            findings.append((
                i,
                f"listen_addresses exposes non-loopback ({value!r})",
                value,
            ))
    return findings


def _hba_token_is_loopback(addr: str) -> bool:
    return addr in LOOPBACK_CIDRS or addr in LOOPBACK or addr in {
        "samehost", "samenet"
    }


def scan_pg_hba(source: str) -> List[Tuple[int, str]]:
    findings: List[Tuple[int, str]] = []
    if SUPPRESS.search(source):
        return findings
    for i, raw in enumerate(source.splitlines(), start=1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        tokens = line.split()
        if not tokens:
            continue
        conn_type = tokens[0].lower()
        # Care about host / hostssl / hostnossl rows.
        if conn_type not in {"host", "hostssl", "hostnossl"}:
            continue
        # Format: host db user address [mask] method [options]
        # Address can be CIDR like 0.0.0.0/0 or hostname or "all" / "samenet".
        if len(tokens) < 5:
            continue
        addr = tokens[3].lower()
        # If addr is not a CIDR-ish thing, the next token may be the mask;
        # for our purposes we only need to know whether addr is loopback or "all".
        method_idx = 4
        # Heuristic: if tokens[4] looks like an IP/mask (contains '.' or ':'),
        # then method is at index 5.
        if len(tokens) >= 6 and (
            re.match(r"^\d+\.\d+\.\d+\.\d+$", tokens[4])
            or ":" in tokens[4]
        ):
            method_idx = 5
        if method_idx >= len(tokens):
            continue
        method = tokens[method_idx].lower()

        is_loopback = _hba_token_is_loopback(addr)
        # "all" in pg_hba address column means any IP -> exposed.
        # CIDRs like 0.0.0.0/0 or ::/0 -> exposed.
        is_world = addr in {"all", "0.0.0.0/0", "::/0"}
        is_exposed = is_world or (not is_loopback)

        if not is_exposed:
            continue

        if method in WEAK_AUTH:
            findings.append((
                i,
                f"pg_hba {conn_type} row uses weak auth {method!r} on non-loopback address {addr!r}",
            ))
    return findings


def _discover_hba_for(conf_path: Path) -> List[Path]:
    out = []
    parent = conf_path.parent
    for cand in sorted(parent.glob("pg_hba*.conf")):
        out.append(cand)
    return out


def scan_paths(paths: Iterable[Path]) -> int:
    bad_files: set = set()
    conf_targets: List[Path] = []
    hba_targets: List[Path] = []

    for path in paths:
        if path.is_dir():
            for cand in sorted(path.rglob("postgresql*.conf")):
                conf_targets.append(cand)
            for cand in sorted(path.rglob("pg_hba*.conf")):
                hba_targets.append(cand)
        elif path.name.startswith("pg_hba") or "pg_hba" in path.name:
            hba_targets.append(path)
        else:
            conf_targets.append(path)
            for sibling in _discover_hba_for(path):
                if sibling not in hba_targets:
                    hba_targets.append(sibling)

    # Scan postgresql.conf files; remember exposed ones.
    exposed_dirs: set = set()
    for f in conf_targets:
        try:
            source = f.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            print(f"{f}:0:read-error: {exc}")
            continue
        hits = scan_postgresql_conf(source)
        if hits:
            bad_files.add(str(f))
            exposed_dirs.add(str(f.parent))
            for line, reason, _value in hits:
                print(f"{f}:{line}:{reason}")

    # Scan pg_hba.conf files independently.
    for f in hba_targets:
        try:
            source = f.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            print(f"{f}:0:read-error: {exc}")
            continue
        hits = scan_pg_hba(source)
        if hits:
            bad_files.add(str(f))
            for line, reason in hits:
                print(f"{f}:{line}:{reason}")
            # Trifecta synthesis: if any sibling postgresql.conf was exposed.
            if str(f.parent) in exposed_dirs:
                print(
                    f"{f}:0:trifecta: exposed listen_addresses + non-loopback pg_hba + weak auth"
                )

    return min(255, len(bad_files))


def main(argv: List[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 0
    return scan_paths([Path(a) for a in argv[1:]])


if __name__ == "__main__":
    sys.exit(main(sys.argv))
