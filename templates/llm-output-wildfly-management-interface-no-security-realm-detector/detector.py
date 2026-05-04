#!/usr/bin/env python3
"""Detect WildFly / JBoss EAP standalone.xml that exposes the
management interface on a non-loopback address with no security
realm or authentication factory.

See README.md for the precise rules. Exit code is the count of files
with at least one finding (capped at 255). Stdout lines have the form
``<file>:<line>:<reason>``.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Iterable, List, Optional, Tuple
from xml.etree import ElementTree as ET

SUPPRESS = re.compile(r"wildfly-mgmt-no-realm-ok")

LOOPBACK_VALUES = {
    "127.0.0.1",
    "::1",
    "[::1]",
    "localhost",
}

PROPERTY_RE = re.compile(r"^\$\{[^:}]+:(?P<default>[^}]*)\}$")

AUTH_ATTRS = (
    "security-realm",
    "http-authentication-factory",
    "sasl-authentication-factory",
)


def _strip_ns(tag: str) -> str:
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def _local(elem: ET.Element) -> str:
    return _strip_ns(elem.tag).lower()


def _iter_local(root: ET.Element, name: str) -> Iterable[ET.Element]:
    name = name.lower()
    for el in root.iter():
        if _local(el) == name:
            yield el


def _resolve_property(value: str) -> str:
    """If value is ``${prop:default}`` return ``default``; else return value."""
    m = PROPERTY_RE.match(value.strip())
    if m:
        return m.group("default").strip()
    return value.strip()


def _is_loopback(value: str) -> bool:
    v = _resolve_property(value)
    if not v:
        # Empty default in property: treat as not-loopback (operator forgot).
        return False
    return v in LOOPBACK_VALUES


def _approx_line(source: str, needle: str) -> int:
    if not needle:
        return 1
    idx = source.find(needle)
    if idx < 0:
        return 1
    return source.count("\n", 0, idx) + 1


def _management_inet_address(root: ET.Element) -> Optional[str]:
    """Return the value attribute of the management interface's
    <inet-address>, or None if the management interface block is
    absent."""
    for iface in _iter_local(root, "interface"):
        if iface.attrib.get("name", "").lower() != "management":
            continue
        for child in iface:
            if _local(child) == "inet-address":
                return child.attrib.get("value", "")
    return None


def _interface_is_unauthenticated(elem: ET.Element) -> bool:
    for attr in AUTH_ATTRS:
        v = elem.attrib.get(attr, "").strip()
        if v:
            return False
    return True


def scan(source: str) -> List[Tuple[int, str]]:
    findings: List[Tuple[int, str]] = []
    if SUPPRESS.search(source):
        return findings

    try:
        root = ET.fromstring(source)
    except ET.ParseError as exc:
        return [(getattr(exc, "position", (1, 0))[0] or 1,
                 f"xml-parse-error: {exc}")]

    bind_value = _management_inet_address(root)
    if bind_value is None:
        # No management interface block defined; nothing to flag.
        return findings

    if _is_loopback(bind_value):
        return findings

    resolved = _resolve_property(bind_value) or bind_value

    # Find <management-interfaces> children.
    mgmt_blocks = list(_iter_local(root, "management-interfaces"))
    if not mgmt_blocks:
        return findings

    for block in mgmt_blocks:
        for iface in block:
            local_name = _local(iface)
            if local_name not in {"http-interface", "native-interface"}:
                continue
            if not _interface_is_unauthenticated(iface):
                continue
            # Approximate line of this interface in source.
            tag_local = local_name
            line = _approx_line(source, f"<{tag_local}")
            findings.append((
                line,
                (
                    f"<{tag_local}> has no security-realm / "
                    f"http-authentication-factory / sasl-authentication-factory "
                    f"and management interface binds to {resolved} — "
                    f"unauthenticated WildFly management"
                ),
            ))

    return findings


def scan_paths(paths: Iterable[Path]) -> int:
    bad_files = 0
    targets: List[Path] = []
    for path in paths:
        if path.is_dir():
            for pat in ("standalone*.xml", "domain*.xml", "host*.xml", "*.xml"):
                targets.extend(sorted(path.rglob(pat)))
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
