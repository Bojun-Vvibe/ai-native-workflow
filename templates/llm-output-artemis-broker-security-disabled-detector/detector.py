#!/usr/bin/env python3
"""Detect ActiveMQ Artemis broker.xml that disables security on a
non-loopback acceptor.

See README.md for the precise rules. Exit code is the count of files
with at least one finding (capped at 255). Stdout lines have the form
``<file>:<line>:<reason>``.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Iterable, List, Tuple
from xml.etree import ElementTree as ET

SUPPRESS = re.compile(r"artemis-security-disabled-ok")

LOOPBACK_HOSTS = {
    "127.0.0.1",
    "::1",
    "[::1]",
    "localhost",
    "ip6-localhost",
}

# Match URIs of the shape: tcp://HOST:PORT?params  (Artemis acceptor URI).
# HOST may be IPv4, hostname, [::ipv6], or empty (all interfaces).
ACCEPTOR_URI_RE = re.compile(
    r"""^\s*
        (?P<scheme>[a-zA-Z0-9+.-]+)://
        (?P<host>\[[^\]]*\]|[^:/?\s]*)
        (?::(?P<port>\d+))?
    """,
    re.VERBOSE,
)


def _strip_ns(tag: str) -> str:
    """Return local-name from a possibly-namespaced ElementTree tag."""
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def _line_of(elem: ET.Element) -> int:
    return getattr(elem, "sourceline", 0) or 0


def _iter_local(root: ET.Element, name: str) -> Iterable[ET.Element]:
    name = name.lower()
    for el in root.iter():
        if _strip_ns(el.tag).lower() == name:
            yield el


def _is_public_host(host: str) -> bool:
    h = host.strip()
    if not h:
        # Empty host on a tcp:// acceptor URI means "all interfaces" in
        # Artemis. Treat as public.
        return True
    if h in LOOPBACK_HOSTS:
        return False
    # Strip brackets for IPv6 normalization.
    if h.startswith("[") and h.endswith("]"):
        inner = h[1:-1]
        if inner in {"::1"}:
            return False
    return True


def _approx_line_for_text(source: str, needle: str) -> int:
    if not needle:
        return 1
    idx = source.find(needle)
    if idx < 0:
        return 1
    return source.count("\n", 0, idx) + 1


def scan(source: str, path_label: str = "<text>") -> List[Tuple[int, str]]:
    findings: List[Tuple[int, str]] = []
    if SUPPRESS.search(source):
        return findings

    try:
        root = ET.fromstring(source)
    except ET.ParseError as exc:
        return [(getattr(exc, "position", (1, 0))[0] or 1,
                 f"xml-parse-error: {exc}")]

    # Find any <security-enabled>false</security-enabled>.
    sec_disabled_line = 0
    for el in _iter_local(root, "security-enabled"):
        text = (el.text or "").strip().lower()
        if text == "false":
            # ElementTree (stdlib) does not record source lines reliably
            # without iterparse. Approximate by searching the source.
            sec_disabled_line = _approx_line_for_text(
                source, "<security-enabled>false</security-enabled>"
            )
            if sec_disabled_line == 1:
                # Try with whitespace.
                m = re.search(
                    r"<security-enabled>\s*false\s*</security-enabled>",
                    source,
                    re.IGNORECASE,
                )
                if m:
                    sec_disabled_line = source.count("\n", 0, m.start()) + 1
            break

    if not sec_disabled_line:
        return findings

    # Walk acceptors. Each <acceptor> element has the URI as element text.
    public_acceptors: List[Tuple[int, str, str]] = []
    for el in _iter_local(root, "acceptor"):
        uri = (el.text or "").strip()
        if not uri:
            continue
        m = ACCEPTOR_URI_RE.match(uri)
        if not m:
            continue
        host = m.group("host") or ""
        port = m.group("port") or "?"
        if _is_public_host(host):
            # Approximate line of this acceptor in source.
            name_attr = el.attrib.get("name", "")
            search_token = f'name="{name_attr}"' if name_attr else uri[:40]
            line = _approx_line_for_text(source, search_token)
            host_desc = host if host else "<all interfaces>"
            public_acceptors.append((line, host_desc, port))

    if not public_acceptors:
        return findings

    for line, host_desc, port in public_acceptors:
        findings.append((
            line,
            (
                f"<security-enabled>false</security-enabled> with public "
                f"acceptor host={host_desc} port={port} — open Artemis broker"
            ),
        ))
    return findings


def scan_paths(paths: Iterable[Path]) -> int:
    bad_files = 0
    targets: List[Path] = []
    for path in paths:
        if path.is_dir():
            for pat in ("broker.xml", "*broker*.xml", "*.xml"):
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
        hits = scan(source, str(f))
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
