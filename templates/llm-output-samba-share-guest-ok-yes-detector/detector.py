#!/usr/bin/env python3
"""Detect Samba (smb.conf) share definitions that allow guest (no
password) access via ``guest ok = yes`` without restricting writes or
the listening interface.

See README.md for the precise rules. Exit code is the count of files
with at least one finding (capped at 255). Stdout lines have the form
``<file>:<line>:<reason>``.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

SUPPRESS = re.compile(r"#\s*smb-guest-allowed")

SECTION_RE = re.compile(r"^\s*\[\s*([^\]]+?)\s*\]\s*$")
KEYVAL_RE = re.compile(r"^\s*([A-Za-z][\w \-]*?)\s*=\s*(.+?)\s*$")

# Keys that have whitespace-insensitive aliases in Samba.
GUEST_OK_KEYS = {"guest ok", "public"}
GUEST_ONLY_KEYS = {"guest only", "only guest"}

TRUTHY = {"yes", "true", "1", "on"}
FALSY = {"no", "false", "0", "off"}


def _norm_key(k: str) -> str:
    # Samba treats "guest ok", "guest_ok", "guestok" as equivalent in
    # practice; collapse whitespace and underscores.
    return re.sub(r"[\s_]+", " ", k.strip().lower())


def _to_bool(v: str) -> Optional[bool]:
    s = v.strip().lower()
    if s in TRUTHY:
        return True
    if s in FALSY:
        return False
    return None


class Section:
    __slots__ = ("name", "open_line", "kv", "key_lines")

    def __init__(self, name: str, open_line: int) -> None:
        self.name = name
        self.open_line = open_line
        self.kv: Dict[str, str] = {}
        self.key_lines: Dict[str, int] = {}

    def get_bool(self, *keys: str) -> Tuple[Optional[bool], int]:
        for k in keys:
            if k in self.kv:
                return _to_bool(self.kv[k]), self.key_lines.get(k, self.open_line)
        return None, self.open_line

    def get_str(self, key: str) -> Optional[str]:
        return self.kv.get(key)


def _is_loopback_iface(value: str) -> bool:
    tokens = [t.strip().lower() for t in re.split(r"[\s,]+", value) if t.strip()]
    if not tokens:
        return False
    for t in tokens:
        if t in {"127.0.0.1", "::1", "localhost", "lo"}:
            continue
        if t.startswith("127."):
            continue
        return False
    return True


def scan(source: str) -> List[Tuple[int, str]]:
    findings: List[Tuple[int, str]] = []
    if SUPPRESS.search(source):
        return findings

    sections: List[Section] = []
    current: Optional[Section] = None

    for i, raw in enumerate(source.splitlines(), start=1):
        # Samba supports ; and # comments.
        line = raw.split("#", 1)[0]
        line = line.split(";", 1)[0]
        if not line.strip():
            continue

        m = SECTION_RE.match(line)
        if m:
            name = m.group(1).strip().lower()
            current = Section(name=name, open_line=i)
            sections.append(current)
            continue

        if current is None:
            # Stray key/value before any section: treat as part of a
            # synthetic [global] so we still see it.
            current = Section(name="global", open_line=i)
            sections.append(current)

        m = KEYVAL_RE.match(line)
        if m:
            k = _norm_key(m.group(1))
            v = m.group(2).strip()
            current.kv[k] = v
            current.key_lines[k] = i

    # Pull global defaults that affect the verdict.
    global_section: Optional[Section] = None
    for s in sections:
        if s.name == "global":
            global_section = s
            break

    g_interfaces_loopback = False
    g_bind_interfaces_only = False
    g_map_to_guest = ""
    if global_section is not None:
        ifaces = global_section.get_str("interfaces")
        if ifaces and _is_loopback_iface(ifaces):
            g_interfaces_loopback = True
        biob, _ = global_section.get_bool("bind interfaces only")
        if biob is True:
            g_bind_interfaces_only = True
        g_map_to_guest = (global_section.get_str("map to guest") or "").strip().lower()

    listener_is_loopback = g_interfaces_loopback and g_bind_interfaces_only

    # If the server cannot map any incoming user to the guest account,
    # `guest ok = yes` shares are effectively dead (still a smell, but
    # not directly exploitable as anonymous access). Samba defaults to
    # "never" if `map to guest` is missing.
    guest_mapping_active = g_map_to_guest in {"bad user", "bad password", "bad uid"}

    for sec in sections:
        if sec.name in {"global", "printers", "print$"}:
            continue
        guest_ok, guest_line = sec.get_bool(*GUEST_OK_KEYS)
        if guest_ok is not True:
            continue
        # If global blocks all guest mapping, this share is not actually
        # exploitable; do not flag.
        if not guest_mapping_active:
            continue
        # Loopback-bound smbd is not network-exposed.
        if listener_is_loopback:
            continue
        # writable=yes / read only=no escalates the impact, but a
        # readable open share is already a finding.
        writable, _ = sec.get_bool("writable", "writeable", "write ok")
        read_only, _ = sec.get_bool("read only")
        is_writable = (writable is True) or (read_only is False)

        path = sec.get_str("path") or "<unspecified>"
        impact = "write" if is_writable else "read"
        findings.append(
            (
                guest_line,
                (
                    f"share [{sec.name}] path={path} has guest ok=yes with "
                    f"map to guest='{g_map_to_guest or 'never'}' — "
                    f"anonymous {impact} access over SMB"
                ),
            )
        )

    return findings


def scan_paths(paths: Iterable[Path]) -> int:
    bad_files = 0
    targets: List[Path] = []
    for path in paths:
        if path.is_dir():
            for ext in ("smb.conf", "*.smb.conf", "*.conf"):
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
