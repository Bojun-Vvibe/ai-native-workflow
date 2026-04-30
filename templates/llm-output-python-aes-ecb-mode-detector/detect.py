#!/usr/bin/env python3
"""Detect AES-ECB (and DES/3DES/Blowfish-ECB) usage in LLM-emitted Python.

ECB ("Electronic Code Book") is the textbook block-cipher mode that
encrypts every block independently with the same key. Identical
plaintext blocks therefore produce identical ciphertext blocks,
which:

* Leaks structural information (the canonical "ECB penguin" image).
* Allows block reordering / replay attacks.
* Is rejected by every modern crypto guidance (NIST SP 800-38A
  permits it but warns; FIPS profiles avoid it; OWASP forbids it).

LLMs emit ECB mode by reflex because:

1. It is the simplest mode (no IV / nonce parameter).
2. It is what most "AES in Python" Stack Overflow answers from
   2009-2015 use as the introductory example.
3. Asking "encrypt this with AES" without specifying a mode often
   yields ECB because the model is trying to minimise required
   parameters.

CWE references
--------------
* **CWE-327**: Use of a Broken or Risky Cryptographic Algorithm.
* **CWE-696**: Incorrect Behavior Order — using ECB where chaining
  is needed.
* **CWE-1240**: Use of a Cryptographic Primitive with a Risky
  Implementation.

What this flags
---------------
* `pycryptodome` / `pycrypto` style:
  - `AES.new(key, AES.MODE_ECB)`
  - `DES.new(key, DES.MODE_ECB)`
  - `DES3.new(key, DES3.MODE_ECB)`
  - `Blowfish.new(key, Blowfish.MODE_ECB)`
  - Bare `MODE_ECB` constant references on a cipher line.
* `cryptography.hazmat` style:
  - `Cipher(algorithms.AES(key), modes.ECB())`
  - `modes.ECB()` standalone call.
* `pyca/cryptography` legacy: `algorithms.TripleDES(key)` paired
  with `modes.ECB()`.

What this does NOT flag
-----------------------
* Safe modes: `MODE_CBC`, `MODE_CTR`, `MODE_GCM`, `MODE_OCB`,
  `modes.GCM(...)`, `modes.CTR(...)`, `modes.CBC(...)`.
* `AES-ECB` mentioned in a `#` comment or string literal.
* Lines suffixed with the suppression marker `# aes-ecb-ok`
  (e.g. for KAT/test vectors where ECB is required by spec).

Usage
-----
    python3 detect.py <file_or_dir> [...]

Exit 1 if any findings, 0 otherwise. python3 stdlib only.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

SUPPRESS = "# aes-ecb-ok"

# pycryptodome: `<Cipher>.new(key, <Cipher>.MODE_ECB[, ...])`
RE_PYCRYPTO_MODE_ECB = re.compile(
    r"\b(?:AES|DES|DES3|Blowfish|ARC2|CAST)\.MODE_ECB\b"
)

# Bare `MODE_ECB` — covers `from Crypto.Cipher.AES import MODE_ECB` then
# `AES.new(key, MODE_ECB)`.
RE_BARE_MODE_ECB = re.compile(r"(?<![A-Za-z0-9_])MODE_ECB(?![A-Za-z0-9_])")

# pyca/cryptography: `modes.ECB()`
RE_MODES_ECB = re.compile(r"\bmodes\s*\.\s*ECB\s*\(")

# pyca/cryptography: `from ... import ECB` then `Cipher(..., ECB())`.
# We need an anchor: a line that has both a Cipher( call and ECB( on it,
# or an `ECB()` call following an algorithms reference.
RE_ECB_CALL = re.compile(r"(?<![A-Za-z0-9_.])ECB\s*\(\s*\)")
RE_CIPHER_CALL = re.compile(r"\bCipher\s*\(")
RE_ALGORITHMS = re.compile(r"\balgorithms\s*\.\s*(?:AES|TripleDES|Blowfish|CAST5|IDEA|SEED)\b")


def _strip_comment_and_strings(line: str) -> str:
    """Replace string-literal contents with spaces, drop `#` comments."""
    out = []
    in_s = False
    quote = ""
    i = 0
    while i < len(line):
        ch = line[i]
        if in_s:
            if ch == "\\" and i + 1 < len(line):
                out.append("  ")
                i += 2
                continue
            if ch == quote:
                in_s = False
                out.append(ch)
            else:
                out.append(" ")
        else:
            if ch == "#":
                break
            if ch in ("'", '"'):
                in_s = True
                quote = ch
                out.append(ch)
            else:
                out.append(ch)
        i += 1
    return "".join(out)


def scan_file(path: Path) -> list[tuple[Path, int, str, str]]:
    findings: list[tuple[Path, int, str, str]] = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return findings
    for lineno, raw in enumerate(text.splitlines(), start=1):
        if SUPPRESS in raw:
            continue
        line = _strip_comment_and_strings(raw)
        if "ECB" not in line:
            continue
        if RE_PYCRYPTO_MODE_ECB.search(line):
            findings.append((path, lineno, "aes-ecb-pycrypto-mode", raw.rstrip()))
            continue
        if RE_MODES_ECB.search(line):
            findings.append((path, lineno, "aes-ecb-pyca-modes-call", raw.rstrip()))
            continue
        # `from ... import MODE_ECB` is a smell, but the actual misuse is
        # using it. Flag any non-import bare `MODE_ECB` use.
        if RE_BARE_MODE_ECB.search(line) and not re.match(r"^\s*(?:from|import)\b", line):
            findings.append((path, lineno, "aes-ecb-bare-mode", raw.rstrip()))
            continue
        # pyca: `Cipher(algorithms.AES(key), ECB())` on one line.
        if RE_ECB_CALL.search(line) and (
            RE_CIPHER_CALL.search(line) or RE_ALGORITHMS.search(line)
        ):
            findings.append((path, lineno, "aes-ecb-pyca-bare-call", raw.rstrip()))
            continue
    return findings


def iter_paths(args: list[str]) -> list[Path]:
    out: list[Path] = []
    for a in args:
        p = Path(a)
        if p.is_file():
            out.append(p)
        elif p.is_dir():
            for sub in sorted(p.rglob("*.py")):
                out.append(sub)
    return out


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: detect.py <file_or_dir> [...]", file=sys.stderr)
        return 2
    findings: list[tuple[Path, int, str, str]] = []
    for path in iter_paths(argv[1:]):
        findings.extend(scan_file(path))
    for path, lineno, kind, line in findings:
        print(f"{path}:{lineno}: {kind}: {line}")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
