#!/usr/bin/env python3
"""Detect Traefik static configs that define a plain-HTTP entrypoint
WITHOUT a redirection to an HTTPS entrypoint.

Traefik supports `entryPoints.<name>.http.redirections.entryPoint.to`
to push every request that arrives on a cleartext entrypoint over to
the HTTPS one (typically named "websecure"). When this redirect is
omitted, browsers and clients keep talking to Traefik on :80 in
cleartext, leaking session cookies and bearer tokens even though
:443 is "available".

Logic:
  1. Find every entrypoint that listens on a cleartext HTTP port
     (:80 or :8080) -- via YAML/TOML `address: ":80"` style, CLI
     flag `--entrypoints.web.address=:80`, or env equivalent.
  2. For each such entrypoint, check if a `redirections.entryPoint.to`
     (or `--entrypoints.<name>.http.redirections.entrypoint.to=...`)
     exists pointing at another entrypoint name.
  3. If at least one cleartext entrypoint has no redirect, print BAD.

Stdlib only.

Usage:
  python3 detector.py <config>
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


# Entry point name + cleartext address in YAML/TOML:
#   web:
#     address: ":80"
# or TOML:
#   [entryPoints.web]
#     address = ":80"
EP_YAML = re.compile(
    r'(?m)^[ \t]*([A-Za-z0-9_-]+)\s*:\s*$'
    r'(?:[ \t]*\n[ \t]+[^\n]*)*?'
    r'[ \t]+address\s*:\s*["\']?:(\d+)["\']?',
)
EP_TOML_HEADER = re.compile(
    r'(?m)^\s*\[entryPoints\.([A-Za-z0-9_-]+)\]\s*$'
    r'(?:[\s\S]*?)'
    r'address\s*=\s*"\s*:(\d+)\s*"',
)
# CLI flag style (works for env KEYS too):
#   --entrypoints.web.address=:80
EP_FLAG = re.compile(
    r'--?entrypoints\.([A-Za-z0-9_-]+)\.address\s*=\s*"?:(\d+)"?',
    re.IGNORECASE,
)

REDIRECT_FLAG = re.compile(
    r'--?entrypoints\.([A-Za-z0-9_-]+)\.http\.redirections\.entry[Pp]oint\.to\s*=',
    re.IGNORECASE,
)
# YAML/TOML redirect under an entrypoint block. We require both the
# entrypoint name to appear earlier and a `redirections:` chunk
# referencing `to:`.
REDIRECT_BLOCK = re.compile(
    r'(?m)^[ \t]*([A-Za-z0-9_-]+)\s*:\s*$'
    r'(?:[ \t]*\n[ \t]+[^\n]*)*?'
    r'redirections\s*:\s*\n'
    r'(?:[ \t]+[^\n]*\n)*?'
    r'[ \t]+to\s*:\s*["\']?[A-Za-z0-9_-]+',
)
REDIRECT_TOML = re.compile(
    r'(?m)\[entryPoints\.([A-Za-z0-9_-]+)\.http\.redirections\.entryPoint\]'
)

CLEARTEXT_PORTS = {"80", "8080"}


def _scan_yaml_entrypoints(text: str) -> dict[str, str]:
    """Walk YAML by indentation, returning {entrypoint_name: port}.

    Looks for a top-level (or nested under entryPoints:) mapping where
    a name's body contains an `address: ":<port>"` line at deeper
    indent than the name itself.
    """
    lines = text.splitlines()
    result: dict[str, str] = {}
    name_re = re.compile(r'^([ \t]*)([A-Za-z0-9_-]+)\s*:\s*$')
    addr_re = re.compile(r'^([ \t]*)address\s*:\s*["\']?:(\d+)["\']?')
    for i, line in enumerate(lines):
        nm = name_re.match(line)
        if not nm:
            continue
        name_indent = len(nm.group(1).expandtabs(2))
        name = nm.group(2)
        # Skip obvious non-entrypoint container keys
        if name in {"entryPoints", "providers", "api", "log", "tls",
                    "certificatesResolvers", "metrics", "tracing",
                    "http", "redirections", "entryPoint", "ports",
                    "command", "additionalArguments"}:
            continue
        # Look forward for an address line at deeper indent until we
        # hit a line at <= name_indent (end of this block).
        for j in range(i + 1, len(lines)):
            nxt = lines[j]
            if not nxt.strip():
                continue
            nxt_indent = len(nxt) - len(nxt.lstrip(" \t"))
            nxt_indent = len(nxt[:nxt_indent].expandtabs(2))
            if nxt_indent <= name_indent:
                break
            am = addr_re.match(nxt)
            if am:
                result[name] = am.group(2)
                break
    return result


def find_cleartext_entrypoints(text: str) -> set[str]:
    found = set()
    for name, port in _scan_yaml_entrypoints(text).items():
        if port in CLEARTEXT_PORTS:
            found.add(name)
    for m in EP_TOML_HEADER.finditer(text):
        if m.group(2) in CLEARTEXT_PORTS:
            found.add(m.group(1))
    for m in EP_FLAG.finditer(text):
        if m.group(2) in CLEARTEXT_PORTS:
            found.add(m.group(1))
    return found


def _scan_yaml_redirects(text: str) -> set[str]:
    """Return the set of entrypoint names that have a redirections.entryPoint.to
    inside their YAML block."""
    lines = text.splitlines()
    result: set[str] = set()
    name_re = re.compile(r'^([ \t]*)([A-Za-z0-9_-]+)\s*:\s*$')
    to_re = re.compile(r'^[ \t]+to\s*:\s*["\']?[A-Za-z0-9_-]+')
    for i, line in enumerate(lines):
        nm = name_re.match(line)
        if not nm:
            continue
        name = nm.group(2)
        name_indent = len(nm.group(1).expandtabs(2))
        if name in {"entryPoints", "providers", "api", "log", "tls",
                    "certificatesResolvers", "metrics", "tracing",
                    "http", "redirections", "entryPoint", "ports",
                    "command", "additionalArguments"}:
            continue
        saw_redirections = False
        for j in range(i + 1, len(lines)):
            nxt = lines[j]
            if not nxt.strip():
                continue
            nxt_indent = len(nxt) - len(nxt.lstrip(" \t"))
            nxt_indent = len(nxt[:nxt_indent].expandtabs(2))
            if nxt_indent <= name_indent:
                break
            stripped = nxt.strip()
            if stripped.startswith("redirections:"):
                saw_redirections = True
            if saw_redirections and to_re.match(nxt):
                result.add(name)
                break
    return result


def find_redirected_entrypoints(text: str) -> set[str]:
    found = set()
    for m in REDIRECT_FLAG.finditer(text):
        found.add(m.group(1))
    found |= _scan_yaml_redirects(text)
    for m in REDIRECT_TOML.finditer(text):
        found.add(m.group(1))
    return found


def looks_bad(text: str) -> bool:
    cleartext = find_cleartext_entrypoints(text)
    if not cleartext:
        return False
    redirected = find_redirected_entrypoints(text)
    # If any cleartext entrypoint lacks a redirect entry, flag.
    return bool(cleartext - redirected)


def strip_comments(text: str) -> str:
    out = []
    for raw in text.splitlines():
        line = raw
        if "#" in line and line.count('"') % 2 == 0 and line.count("'") % 2 == 0:
            line = line.split("#", 1)[0]
        out.append(line)
    return "\n".join(out)


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: detector.py <config-file>", file=sys.stderr)
        return 2
    try:
        text = Path(argv[1]).read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if looks_bad(strip_comments(text)):
        print("BAD")
        return 1
    print("GOOD")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
