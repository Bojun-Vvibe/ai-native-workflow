#!/usr/bin/env python3
"""Detect ``xrdp.ini`` configurations that downgrade the RDP wire to
``crypt_level=none`` or ``crypt_level=low`` while still using the
legacy ``security_layer=rdp`` (or ``negotiate`` allowing a downgrade).

See README.md for the precise rules. Exit code is the count of files
with at least one finding (capped at 255). Stdout lines have the form
``<file>:<line>:<reason>``.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Iterable, List, Tuple

SUPPRESS = re.compile(r"#\s*xrdp-crypt-allowed\b")

SECTION_RE = re.compile(r"^\s*\[([^\]]+)\]\s*$")
KV_RE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_.-]*)\s*=\s*(.*?)\s*$")

# Section names that configure a listener / globals in xrdp.ini.
_GLOBAL_SECTIONS = {"globals", "global", "xrdp", "xrdp1"}

_INSECURE_CRYPT = {"none", "low"}
# 'rdp' = legacy RDP encryption (broken). 'negotiate' allows the
# client to pick — combined with crypt_level low/none it is still
# unsafe because no TLS floor is required.
_INSECURE_SEC_LAYERS = {"rdp", "negotiate"}


def _strip_comment(value: str) -> str:
    # xrdp.ini uses '#' and ';' for comments.
    for marker in ("#", ";"):
        idx = value.find(marker)
        if idx >= 0:
            value = value[:idx]
    return value.strip()


def _parse(source: str) -> List[Tuple[str, str, str, int]]:
    """Return list of (section, key_lower, value_lower, line_no)."""
    out: List[Tuple[str, str, str, int]] = []
    section = ""
    for lineno, raw in enumerate(source.splitlines(), 1):
        line = raw.rstrip()
        if not line.strip() or line.lstrip().startswith(("#", ";")):
            continue
        m = SECTION_RE.match(line)
        if m:
            section = m.group(1).strip().lower()
            continue
        kv = KV_RE.match(line)
        if not kv:
            continue
        key = kv.group(1).strip().lower()
        val = _strip_comment(kv.group(2)).lower()
        out.append((section, key, val, lineno))
    return out


def scan(source: str) -> List[Tuple[int, str]]:
    findings: List[Tuple[int, str]] = []
    if SUPPRESS.search(source):
        return findings

    parsed = _parse(source)
    if not parsed:
        return findings

    # Collect per-section state.
    sections: dict = {}
    for sec, key, val, lineno in parsed:
        bucket = sections.setdefault(sec, {})
        # Keep the first occurrence's line; values can be reset, so we
        # also track the latest value.
        bucket[key] = (val, bucket.get(key, (None, lineno))[1])
        # If we want the *last* seen line for the value, refresh it:
        bucket[key] = (val, lineno)

    flagged = False
    for sec, kvs in sections.items():
        if sec not in _GLOBAL_SECTIONS:
            continue
        crypt = kvs.get("crypt_level", ("high", 0))
        sec_layer = kvs.get("security_layer", ("negotiate", 0))
        tls_only = sec_layer[0] == "tls"
        # Hardened path: tls security layer renders crypt_level moot.
        if tls_only:
            continue
        if crypt[0] not in _INSECURE_CRYPT:
            continue
        if sec_layer[0] not in _INSECURE_SEC_LAYERS:
            # Some other custom layer; do not flag.
            continue
        line = crypt[1] or sec_layer[1] or 1
        reasons = [
            f"[{sec}] crypt_level={crypt[0]} with security_layer="
            f"{sec_layer[0]} (RDP wire is unencrypted or uses broken "
            "legacy RC4)",
        ]
        # Amplifiers
        ssl_proto = kvs.get("ssl_protocols", ("", 0))[0]
        if ssl_proto and ("tlsv1.0" in ssl_proto or "sslv3" in ssl_proto):
            reasons.append(
                f"ssl_protocols includes deprecated {ssl_proto}"
            )
        cert = kvs.get("certificate", ("", 0))[0]
        if not cert:
            reasons.append("no certificate= configured (TLS fallback impossible)")
        findings.append((line, "; ".join(reasons)))
        flagged = True
        # One finding per file is enough; xrdp typically has a single
        # globals block. Keep scanning other sections in case of
        # multi-listener layouts.
    return findings


def scan_paths(paths: Iterable[Path]) -> int:
    bad_files = 0
    targets: List[Path] = []
    for path in paths:
        if path.is_dir():
            for pattern in ("xrdp.ini", "*.xrdp.ini"):
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
