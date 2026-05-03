#!/usr/bin/env python3
"""Detect TiKV configs that ship with empty/missing TLS CA paths.

Scans TiKV TOML config snippets for the `[security]` section and flags
when `ca-path`, `cert-path`, or `key-path` are present but empty (""),
or when the `[security]` block exists but no path keys are set, leaving
the cluster in plaintext mode despite an apparent intent to configure TLS.

Stdlib only. Usage: python3 detector.py <file> [<file>...]
Exit code: number of files flagged (capped at 255).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

SECURITY_HEADER = re.compile(r"^\s*\[security\]\s*$", re.MULTILINE)
NEXT_SECTION = re.compile(r"^\s*\[[^\]]+\]\s*$", re.MULTILINE)
KEY_LINE = re.compile(
    r'^\s*(ca-path|cert-path|key-path)\s*=\s*"(.*?)"\s*(?:#.*)?$',
    re.MULTILINE,
)
TLS_KEYS = ("ca-path", "cert-path", "key-path")


def extract_security_block(text: str) -> str | None:
    m = SECURITY_HEADER.search(text)
    if not m:
        return None
    start = m.end()
    next_match = NEXT_SECTION.search(text, start)
    end = next_match.start() if next_match else len(text)
    return text[start:end]


def analyze(text: str) -> list[str]:
    findings: list[str] = []
    block = extract_security_block(text)
    if block is None:
        return findings
    keys = {k: v for k, v in KEY_LINE.findall(block)}
    # Case A: any TLS key declared but empty string.
    for k in TLS_KEYS:
        if k in keys and keys[k].strip() == "":
            findings.append(f"[security].{k} declared but empty (TLS disabled)")
    # Case B: [security] block exists, but NONE of the TLS keys are present.
    if not any(k in keys for k in TLS_KEYS):
        findings.append(
            "[security] block present but no ca-path/cert-path/key-path set"
        )
    # Case C: ca-path set but cert-path or key-path missing -> half-config.
    if "ca-path" in keys and keys["ca-path"].strip():
        for k in ("cert-path", "key-path"):
            if k not in keys or keys[k].strip() == "":
                findings.append(
                    f"[security].ca-path set but {k} missing/empty (mTLS broken)"
                )
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
