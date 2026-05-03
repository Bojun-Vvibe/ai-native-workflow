#!/usr/bin/env python3
"""Detect HashiCorp Vault server HCL configurations whose ``listener
"tcp"`` block sets ``tls_disable = true`` (or its quoted/integer
equivalents) on a non-loopback bind address.

Vault's HTTP API ships the unseal keys, root tokens, secret reads,
and policy writes for the entire cluster. Disabling TLS on the
listener moves all of that traffic — including the Vault token in
the ``X-Vault-Token`` header on every request — to plaintext on the
network (CWE-319). When combined with a non-loopback ``address`` /
``cluster_address`` (anything other than ``127.0.0.1``,
``[::1]``, ``localhost``, or ``unix://``), any device on the
broadcast domain can capture credentials and impersonate clients.

LLM-generated ``vault.hcl`` / ``server.hcl`` files routinely emit
shapes like::

    listener "tcp" {
      address     = "0.0.0.0:8200"
      tls_disable = true
    }

or::

    listener "tcp" {
      address     = "10.0.1.5:8200"
      tls_disable = "true"
    }

This detector parses each top-level ``listener "tcp" { ... }`` HCL
block and flags blocks where ``tls_disable`` is truthy AND the
``address`` is not a loopback address.

What's checked (per file):
  - ``listener "tcp" { ... }`` blocks (the only listener type Vault
    accepts where TLS is configurable; ``unix`` listeners do not
    have TLS).
  - ``tls_disable`` set to ``true``, ``"true"``, ``1``, ``"1"``,
    ``yes`` (all forms Vault accepts as truthy).
  - ``address`` not in {``127.0.0.1:*``, ``localhost:*``,
    ``[::1]:*``}; missing ``address`` defaults to ``0.0.0.0:8200``
    in Vault and is therefore treated as non-loopback.

Accepted (not flagged):
  - ``tls_disable = false`` (or unset; default is false).
  - Loopback bind (``address = "127.0.0.1:8200"``) even with
    ``tls_disable = true`` — common dev pattern, no network exposure.
  - Files containing the comment ``# vault-tls-disable-allowed``
    are skipped wholesale (intentional dev fixtures).
  - ``listener "unix" { ... }`` blocks (no TLS option exists).

CWE refs:
  - CWE-319: Cleartext Transmission of Sensitive Information
  - CWE-311: Missing Encryption of Sensitive Data
  - CWE-522: Insufficiently Protected Credentials

Usage:
    python3 detector.py <path> [<path> ...]

Exit code: number of files with at least one finding (capped at 255).
Stdout:    ``<file>:<line>:<reason>``.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Iterable, List, Tuple

SUPPRESS = re.compile(r"#\s*vault-tls-disable-allowed", re.IGNORECASE)

# A very small HCL block scanner. We only care about top-level
# `listener "<type>" { ... }` blocks, balanced by counting unescaped
# braces. HCL allows `=` and bare identifiers; values may be quoted.
LISTENER_HEADER_RE = re.compile(
    r'^\s*listener\s+"(?P<type>[^"]+)"\s*\{\s*$'
)
KV_RE = re.compile(
    r'^\s*(?P<key>[A-Za-z_][A-Za-z0-9_-]*)\s*=\s*(?P<value>.+?)\s*(?://.*|#.*)?$'
)

TRUE_VALUES = {"true", '"true"', "1", '"1"', "yes", '"yes"'}

LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1", "[::1]"}


def _strip_quotes(s: str) -> str:
    s = s.strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in {'"', "'"}:
        return s[1:-1]
    return s


def _is_loopback_address(value: str) -> bool:
    """Return True iff the bind address is loopback.

    HCL value here is the raw RHS, possibly quoted. Vault accepts
    ``host:port`` strings.
    """
    raw = _strip_quotes(value)
    if not raw:
        return False
    # Strip port. Handle bracketed IPv6 form.
    host = raw
    if raw.startswith("["):
        end = raw.find("]")
        if end != -1:
            host = raw[: end + 1]
    else:
        if ":" in raw:
            host = raw.rsplit(":", 1)[0]
    return host in LOOPBACK_HOSTS


def _strip_line_comments(line: str) -> str:
    # Drop anything from an unescaped "#" or "//" that isn't inside
    # a string. For the small grammar we use this is fine.
    out = []
    in_str = False
    quote = ""
    i = 0
    while i < len(line):
        ch = line[i]
        if in_str:
            out.append(ch)
            if ch == "\\" and i + 1 < len(line):
                out.append(line[i + 1])
                i += 2
                continue
            if ch == quote:
                in_str = False
        else:
            if ch in ('"', "'"):
                in_str = True
                quote = ch
                out.append(ch)
            elif ch == "#":
                break
            elif ch == "/" and i + 1 < len(line) and line[i + 1] == "/":
                break
            else:
                out.append(ch)
        i += 1
    return "".join(out)


def scan(source: str) -> List[Tuple[int, str]]:
    findings: List[Tuple[int, str]] = []
    if SUPPRESS.search(source):
        return findings

    lines = source.splitlines()
    i = 0
    n = len(lines)
    while i < n:
        raw = lines[i]
        stripped = _strip_line_comments(raw)
        m = LISTENER_HEADER_RE.match(stripped)
        if not m:
            i += 1
            continue

        listener_type = m.group("type")
        header_line = i + 1
        # Walk the block body, tracking brace depth starting at 1
        # (the `{` on the header line).
        depth = 1
        body: List[Tuple[int, str]] = []  # (line_no, content)
        j = i + 1
        while j < n and depth > 0:
            line_clean = _strip_line_comments(lines[j])
            for ch in line_clean:
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
            if depth > 0:
                body.append((j + 1, line_clean))
            j += 1
        i = j  # advance past the closing brace

        if listener_type != "tcp":
            continue

        tls_disable_value = ""
        tls_disable_line = 0
        address_value = ""
        for ln, content in body:
            kv = KV_RE.match(content)
            if not kv:
                continue
            key = kv.group("key").lower()
            val = kv.group("value").strip()
            if key == "tls_disable":
                tls_disable_value = val
                tls_disable_line = ln
            elif key == "address":
                address_value = val

        if tls_disable_value.lower() not in TRUE_VALUES:
            continue

        # tls_disable is truthy. Check bind address.
        if address_value and _is_loopback_address(address_value):
            continue  # loopback only, accepted dev pattern

        bind_repr = (
            _strip_quotes(address_value) if address_value else "0.0.0.0:8200 (default)"
        )
        findings.append(
            (
                tls_disable_line or header_line,
                f'vault listener "tcp" has tls_disable={tls_disable_value} '
                f"on non-loopback bind {bind_repr}",
            )
        )

    return findings


def _is_vault_hcl(path: Path) -> bool:
    name = path.name.lower()
    if name.endswith(".hcl"):
        return True
    if name in {"vault.hcl", "server.hcl"}:
        return True
    return False


def scan_paths(paths: Iterable[Path]) -> int:
    bad_files = 0
    targets: List[Path] = []
    for path in paths:
        if path.is_dir():
            for f in sorted(path.rglob("*")):
                if f.is_file() and _is_vault_hcl(f):
                    targets.append(f)
        else:
            targets.append(path)
    for f in targets:
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
