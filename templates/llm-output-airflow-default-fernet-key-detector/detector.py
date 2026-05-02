#!/usr/bin/env python3
"""Detect Apache Airflow configurations or code that ship with the
well-known *default* / *example* Fernet key, or with `fernet_key`
left blank, or with the literal `YOUR_FERNET_KEY` placeholder.

Background
==========

Airflow encrypts Connection passwords and Variables marked as
"secret" with a single symmetric Fernet key, configured at
`[core] fernet_key` in ``airflow.cfg`` or via the
``AIRFLOW__CORE__FERNET_KEY`` environment variable. Anyone who
holds that key can decrypt every credential in the metadata DB.

LLM-generated snippets very commonly:

  * paste the example key from the Airflow tutorial
    (``YOUR_FERNET_KEY`` literal, or
    ``cryptography.fernet.Fernet.generate_key().decode()`` printed
    once in a public blog post and then copy-pasted everywhere),
  * leave `fernet_key =` empty (Airflow then auto-disables
    encryption and stores Connection passwords in plaintext),
  * hard-code a key that's clearly not from a CSPRNG
    (e.g. ``AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=`` or
    repeating ``a`` / ``0`` patterns).

A file containing the comment marker ``airflow-fernet-key-allowed``
is treated as suppressed.
"""

from __future__ import annotations

import base64
import os
import re
import sys

SUPPRESS_MARK = "airflow-fernet-key-allowed"

# Keys publicly published in Airflow docs / tutorials / Stack Overflow
# answers. These are *examples*, never to be used in production.
KNOWN_PUBLIC_KEYS = {
    # From the official Airflow security tutorial example output.
    "cryptography_not_found_storing_passwords_in_plain_text",
    # The literal placeholder in the docs.
    "YOUR_FERNET_KEY",
    # The "hello world" key copied around in countless blog posts.
    "ZmDfcTF7_60GrrY167zsiPd67pEvs0aGOv2oasOM1Pg=",
    "47DEQpj8HBSa-_TImW-5JCeuQeRkm5NMpJWZG3hSuFU=",
}

# `fernet_key = <value>` in airflow.cfg or env file.
CFG_LINE = re.compile(
    r"""^[ \t]*fernet_key[ \t]*=[ \t]*([^\r\n#]*)""",
    re.IGNORECASE | re.MULTILINE,
)

# `AIRFLOW__CORE__FERNET_KEY=<value>` in shell / Dockerfile / env.
ENV_LINE = re.compile(
    r"""(?:^|[\s'";])AIRFLOW__CORE__FERNET_KEY\s*=\s*['"]?([^\s'"\n#]*)""",
    re.IGNORECASE | re.MULTILINE,
)


def _is_obviously_weak(key: str) -> str | None:
    """Return a reason string if `key` is obviously bad, else None."""
    k = key.strip().strip('"').strip("'")
    if k == "":
        return "fernet_key is empty — Airflow stores connection passwords in plaintext"
    if k in KNOWN_PUBLIC_KEYS:
        return f"fernet_key is a publicly published example value ('{k[:16]}...')"
    if k.upper() in {"YOUR_FERNET_KEY", "CHANGEME", "CHANGE_ME", "REPLACE_ME", "TODO", "FIXME"}:
        return f"fernet_key is a placeholder literal ('{k}')"
    # Single-character repetition (e.g. AAAAAAAA…=, 00000000…=).
    body = k.rstrip("=")
    if len(body) >= 8 and len(set(body)) == 1:
        return f"fernet_key is a single-char repetition ('{body[0]}'×{len(body)}) — not from a CSPRNG"
    # Must base64-decode to exactly 32 bytes for a real Fernet key.
    try:
        raw = base64.urlsafe_b64decode(k + "=" * (-len(k) % 4))
    except Exception:
        return f"fernet_key is not valid urlsafe base64 ('{k[:16]}...')"
    if len(raw) != 32:
        return (
            f"fernet_key decodes to {len(raw)} bytes, not 32 — "
            f"not a valid Fernet key"
        )
    # All-zero / all-0xff raw bytes.
    if raw == b"\x00" * 32 or raw == b"\xff" * 32:
        return "fernet_key raw bytes are all 0x00 / 0xff — not from a CSPRNG"
    return None


def scan_file(path: str) -> list[str]:
    try:
        text = open(path, "r", encoding="utf-8", errors="replace").read()
    except OSError as exc:
        return [f"{path}: cannot read: {exc}"]

    if SUPPRESS_MARK in text:
        return []

    findings: list[str] = []
    seen: set[str] = set()

    for m in CFG_LINE.finditer(text):
        val = m.group(1)
        reason = _is_obviously_weak(val)
        if reason and reason not in seen:
            findings.append(f"{path}: [core] {reason}")
            seen.add(reason)

    for m in ENV_LINE.finditer(text):
        val = m.group(1)
        reason = _is_obviously_weak(val)
        if reason and reason not in seen:
            findings.append(f"{path}: AIRFLOW__CORE__FERNET_KEY: {reason}")
            seen.add(reason)

    return findings


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: detector.py <file> [file ...]", file=sys.stderr)
        return 2
    files: list[str] = []
    for arg in argv[1:]:
        if os.path.isdir(arg):
            for root, _, names in os.walk(arg):
                for name in names:
                    files.append(os.path.join(root, name))
        else:
            files.append(arg)

    total = 0
    for f in files:
        for finding in scan_file(f):
            print(finding)
            total += 1
    return total


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
