#!/usr/bin/env python3
"""Detect Mosquitto MQTT broker configs that allow anonymous clients on
a non-loopback listener with no auth backend.

See README.md for the precise rules. Exit code is the count of files
with at least one finding (capped at 255). Stdout lines have the form
``<file>:<line>:<reason>``.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Iterable, List, Tuple

SUPPRESS = re.compile(r"#\s*mqtt-anonymous-allowed")

LISTENER_RE = re.compile(r"^\s*listener\s+(\d+)(?:\s+(\S+))?", re.IGNORECASE)
PORT_RE = re.compile(r"^\s*port\s+(\d+)", re.IGNORECASE)
BIND_ADDRESS_RE = re.compile(r"^\s*bind_address\s+(\S+)", re.IGNORECASE)
ALLOW_ANON_RE = re.compile(r"^\s*allow_anonymous\s+(true|false)\b", re.IGNORECASE)
PASSWORD_FILE_RE = re.compile(r"^\s*password_file\s+\S+", re.IGNORECASE)
PSK_FILE_RE = re.compile(r"^\s*psk_file\s+\S+", re.IGNORECASE)
AUTH_PLUGIN_RE = re.compile(r"^\s*auth_plugin\s+\S+", re.IGNORECASE)
REQUIRE_CERT_RE = re.compile(r"^\s*require_certificate\s+true\b", re.IGNORECASE)
USE_IDENT_RE = re.compile(r"^\s*use_identity_as_username\s+true\b", re.IGNORECASE)

LOOPBACK = {"127.0.0.1", "::1", "localhost"}


class Listener:
    __slots__ = (
        "line",
        "port",
        "bind",
        "allow_anonymous",
        "has_password_file",
        "has_psk",
        "has_plugin",
        "require_cert",
        "use_identity",
    )

    def __init__(self, line: int, port: str, bind: str) -> None:
        self.line = line
        self.port = port
        self.bind = bind
        self.allow_anonymous = None  # tri-state: None / True / False
        self.has_password_file = False
        self.has_psk = False
        self.has_plugin = False
        self.require_cert = False
        self.use_identity = False

    def is_loopback_only(self) -> bool:
        return self.bind in LOOPBACK

    def is_authenticated(self) -> bool:
        if self.has_password_file or self.has_psk or self.has_plugin:
            return True
        if self.require_cert and self.use_identity:
            return True
        return False


def scan(source: str) -> List[Tuple[int, str]]:
    findings: List[Tuple[int, str]] = []
    if SUPPRESS.search(source):
        return findings

    # Global state (applies until first listener block).
    global_listener = Listener(line=0, port="1883", bind="")
    listeners: List[Listener] = []
    current: Listener = global_listener

    saw_explicit_listener = False

    for i, raw in enumerate(source.splitlines(), start=1):
        stripped = raw.split("#", 1)[0]
        if not stripped.strip():
            continue

        m = LISTENER_RE.match(stripped)
        if m:
            saw_explicit_listener = True
            port = m.group(1)
            bind = (m.group(2) or "").strip()
            current = Listener(line=i, port=port, bind=bind)
            # Inherit global allow_anonymous as the starting default if
            # global was set, but the listener can override.
            current.allow_anonymous = global_listener.allow_anonymous
            current.has_password_file = global_listener.has_password_file
            current.has_psk = global_listener.has_psk
            current.has_plugin = global_listener.has_plugin
            listeners.append(current)
            continue

        m = PORT_RE.match(stripped)
        if m and not saw_explicit_listener:
            current.port = m.group(1)
            if current.line == 0:
                current.line = i
            continue

        m = BIND_ADDRESS_RE.match(stripped)
        if m:
            current.bind = m.group(1).strip()
            continue

        m = ALLOW_ANON_RE.match(stripped)
        if m:
            val = m.group(1).lower() == "true"
            current.allow_anonymous = val
            if not saw_explicit_listener:
                global_listener.allow_anonymous = val
            # Track the line where it was set on this listener for
            # accurate finding location.
            if val and current is not global_listener:
                current.line = i
            elif val and current is global_listener:
                global_listener.line = i
            continue

        if PASSWORD_FILE_RE.match(stripped):
            current.has_password_file = True
            continue
        if PSK_FILE_RE.match(stripped):
            current.has_psk = True
            continue
        if AUTH_PLUGIN_RE.match(stripped):
            current.has_plugin = True
            continue
        if REQUIRE_CERT_RE.match(stripped):
            current.require_cert = True
            continue
        if USE_IDENT_RE.match(stripped):
            current.use_identity = True
            continue

    # If no explicit listener block, the global "default listener" is
    # the only listener.
    if not listeners:
        listeners = [global_listener]

    for lst in listeners:
        if lst.allow_anonymous is not True:
            continue
        if lst.is_loopback_only():
            continue
        if lst.is_authenticated():
            continue
        bind_desc = lst.bind if lst.bind else "<all interfaces>"
        line = lst.line if lst.line else 1
        findings.append((
            line,
            (
                f"listener port={lst.port} bind={bind_desc} has "
                "allow_anonymous true with no password_file / psk_file / "
                "auth_plugin — open MQTT broker"
            ),
        ))

    return findings


def scan_paths(paths: Iterable[Path]) -> int:
    bad_files = 0
    targets: List[Path] = []
    for path in paths:
        if path.is_dir():
            for ext in ("mosquitto.conf", "*.mosquitto.conf", "*.conf"):
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
