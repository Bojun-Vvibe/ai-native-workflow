#!/usr/bin/env python3
"""Detect Varnish VCL files that handle PURGE/BAN without an ACL gate.

Varnish convention: define an `acl purge { ... }` block listing trusted
client IPs, then in `vcl_recv` check `if (req.method == "PURGE") { if
(!client.ip ~ purge) { return (synth(405)); } return (purge); }`.

LLM-generated VCL frequently:
  1. Handles PURGE/BAN with no `acl` block at all.
  2. Defines an `acl` block but forgets the `client.ip ~ acl` check
     before `return (purge)` / `ban(...)`.
  3. Defines an ACL that contains "0.0.0.0"/0 or "any" (effectively
     world-open).

Stdlib only. Usage: python3 detector.py <file> [<file>...]
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ACL_BLOCK = re.compile(r'\bacl\s+(\w+)\s*\{([^}]*)\}', re.DOTALL)
PURGE_OR_BAN = re.compile(r'\b(PURGE|BAN)\b')
RETURN_PURGE = re.compile(r'\breturn\s*\(\s*purge\s*\)')
BAN_CALL = re.compile(r'\bban\s*\(')
CLIENT_IP_ACL_CHECK = re.compile(r'client\.ip\s*~\s*\w+')
WORLD_OPEN_ENTRY = re.compile(r'"\s*0\.0\.0\.0\s*"\s*/\s*0|"\s*0\.0\.0\.0/0\s*"|"\s*any\s*"', re.IGNORECASE)


def strip_comments(text: str) -> str:
    # Strip VCL/C-style line comments and block comments before structural checks
    # so that hints inside `# ...`, `// ...`, or `/* ... */` don't confuse the
    # ACL-gate check.
    text = re.sub(r'/\*.*?\*/', '', text, flags=re.DOTALL)
    text = re.sub(r'//[^\n]*', '', text)
    text = re.sub(r'#[^\n]*', '', text)
    return text


def analyze(text: str) -> list[str]:
    findings: list[str] = []
    code = strip_comments(text)

    handles_purge = bool(RETURN_PURGE.search(code)) or bool(BAN_CALL.search(code))
    mentions_purge = bool(PURGE_OR_BAN.search(code))

    if not (handles_purge or mentions_purge):
        return findings

    acls = ACL_BLOCK.findall(code)
    has_ip_check = bool(CLIENT_IP_ACL_CHECK.search(code))

    # Case 1: handles PURGE/BAN but no acl block at all.
    if handles_purge and not acls:
        findings.append(
            "VCL handles PURGE/BAN but defines no `acl` block — anyone can purge cache"
        )

    # Case 2: acl block(s) exist but no `client.ip ~ <acl>` check anywhere.
    if handles_purge and acls and not has_ip_check:
        names = ", ".join(name for name, _ in acls)
        findings.append(
            f"VCL defines acl block(s) [{names}] but never checks client.ip against them"
        )

    # Case 3: world-open ACL entries.
    for name, body in acls:
        if WORLD_OPEN_ENTRY.search(body):
            findings.append(
                f"acl `{name}` contains a world-open entry (0.0.0.0/0 or \"any\")"
            )

    # Case 4: PURGE/BAN keyword referenced in vcl_recv path but neither
    # return(purge) nor ban() is gated. Detected via mentions_purge with
    # no acl + no ip check (covered by 1 and 2 above); skip extra noise.

    return findings


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: detector.py <file> [<file>...]", file=sys.stderr)
        return 2
    flagged = 0
    for path_str in argv[1:]:
        p = Path(path_str)
        try:
            text = p.read_text(encoding="utf-8")
        except OSError as e:
            print(f"{p}: ERROR {e}", file=sys.stderr)
            continue
        findings = analyze(text)
        if findings:
            flagged += 1
            print(f"{p}: FLAGGED")
            for f in findings:
                print(f"  - {f}")
        else:
            print(f"{p}: ok")
    print(f"summary: {flagged}/{len(argv)-1} flagged")
    return min(flagged, 255)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
