#!/usr/bin/env python3
"""Detect Python source that constructs an `ssl.SSLContext` with certificate
verification disabled.

The disastrous shapes this catches:

    ctx = ssl._create_unverified_context()         # CWE-295
    ctx = ssl._create_stdlib_context()             # silently CERT_NONE
    ctx.check_hostname = False                     # disables SNI/CN check
    ctx.verify_mode = ssl.CERT_NONE                # disables chain check
    ssl._create_default_https_context = ssl._create_unverified_context  # global!

LLMs love these patterns because they make a self-signed cert "just work"
for a demo. In production they neuter TLS: any attacker who can MITM the
connection can present any certificate and the client accepts it.

What this flags
---------------
* `ssl._create_unverified_context(...)` calls
* `ssl._create_stdlib_context(...)` calls (defaults to CERT_NONE on <3.4
  paths LLMs still emit)
* Assignment `<anything>.check_hostname = False`
* Assignment `<anything>.verify_mode = ssl.CERT_NONE` (or bare `CERT_NONE`)
* Re-assignment of `ssl._create_default_https_context`

What this does NOT flag
-----------------------
* Comments and string literals containing the names
* Lines marked with a trailing `# ssl-ok` comment
* `ctx.verify_mode = ssl.CERT_REQUIRED` or `CERT_OPTIONAL`

Usage
-----
    python3 detect.py <file_or_dir> [...]

Exit code 1 if any findings, 0 otherwise. python3 stdlib only.
Pure single-pass line scanner — does not import `ast` so it stays
robust against syntactically broken snippets.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


RE_UNVERIFIED_CALL = re.compile(r"\bssl\._create_unverified_context\s*\(")
RE_STDLIB_CTX_CALL = re.compile(r"\bssl\._create_stdlib_context\s*\(")
RE_DEFAULT_HTTPS = re.compile(
    r"\bssl\._create_default_https_context\s*=\s*ssl\._create_unverified_context\b"
)
RE_CHECK_HOSTNAME_FALSE = re.compile(
    r"\b[A-Za-z_][A-Za-z0-9_\.]*\.check_hostname\s*=\s*False\b"
)
RE_VERIFY_MODE_NONE = re.compile(
    r"\b[A-Za-z_][A-Za-z0-9_\.]*\.verify_mode\s*=\s*(?:ssl\.)?CERT_NONE\b"
)
RE_SUPPRESS = re.compile(r"#\s*ssl-ok\b")


def strip_comments_and_strings(line: str, in_triple: str | None) -> tuple[str, str | None]:
    """Return the line with comments and string contents replaced by spaces.

    Tracks triple-quoted strings across lines via the returned state.
    Single-quoted strings are handled within the line.
    """
    out: list[str] = []
    i = 0
    n = len(line)
    in_str: str | None = in_triple
    while i < n:
        ch = line[i]
        if in_str is None:
            if ch == "#":
                out.append(" " * (n - i))
                break
            if ch in ("'", '"'):
                if line[i:i + 3] in ("'''", '"""'):
                    in_str = line[i:i + 3]
                    out.append("   ")
                    i += 3
                    continue
                in_str = ch
                out.append(" ")
                i += 1
                continue
            out.append(ch)
            i += 1
        else:
            if len(in_str) == 3:
                if line[i:i + 3] == in_str:
                    in_str = None
                    out.append("   ")
                    i += 3
                    continue
                out.append(" ")
                i += 1
            else:
                if ch == "\\" and i + 1 < n:
                    out.append("  ")
                    i += 2
                    continue
                if ch == in_str:
                    in_str = None
                    out.append(" ")
                    i += 1
                    continue
                out.append(" ")
                i += 1
    # Triple-quoted strings persist; single-quoted strings should not.
    if in_str is not None and len(in_str) == 1:
        in_str = None
    return "".join(out), in_str


def scan_file(path: Path) -> list[tuple[int, str, str]]:
    findings: list[tuple[int, str, str]] = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return findings
    in_triple: str | None = None
    for lineno, raw in enumerate(text.splitlines(), start=1):
        if RE_SUPPRESS.search(raw):
            # still need to advance string state
            _, in_triple = strip_comments_and_strings(raw, in_triple)
            continue
        stripped, in_triple = strip_comments_and_strings(raw, in_triple)
        for rx, label in (
            (RE_UNVERIFIED_CALL, "ssl-no-verify: ssl._create_unverified_context()"),
            (RE_STDLIB_CTX_CALL, "ssl-no-verify: ssl._create_stdlib_context()"),
            (RE_DEFAULT_HTTPS, "ssl-no-verify: global default HTTPS context disabled"),
            (RE_CHECK_HOSTNAME_FALSE, "ssl-no-verify: check_hostname = False"),
            (RE_VERIFY_MODE_NONE, "ssl-no-verify: verify_mode = CERT_NONE"),
        ):
            if rx.search(stripped):
                findings.append((lineno, label, raw.rstrip()))
    return findings


def iter_targets(args: list[str]):
    for a in args:
        p = Path(a)
        if p.is_dir():
            for sub in sorted(p.rglob("*.py")):
                yield sub
        elif p.is_file():
            yield p


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 0
    any_finding = False
    for path in iter_targets(argv[1:]):
        for lineno, label, raw in scan_file(path):
            any_finding = True
            print(f"{path}:{lineno}: {label} :: {raw.strip()}")
    return 1 if any_finding else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
