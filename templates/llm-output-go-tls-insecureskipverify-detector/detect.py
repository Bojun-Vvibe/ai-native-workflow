#!/usr/bin/env python3
"""Detect ``InsecureSkipVerify: true`` and equivalents in LLM-emitted Go.

LLMs emitting Go HTTP / gRPC / database client code commonly write::

    tlsCfg := &tls.Config{InsecureSkipVerify: true}
    cfg := tls.Config{InsecureSkipVerify: true}
    client := &http.Client{Transport: &http.Transport{
        TLSClientConfig: &tls.Config{InsecureSkipVerify: true},
    }}
    creds := credentials.NewTLS(&tls.Config{InsecureSkipVerify: true})

…to "make the cert error go away" during a PoC. This disables peer
certificate validation entirely: any attacker on path can MITM the
TLS connection. The ``crypto/tls`` package's own godoc says it
"should be used only for testing or in combination with VerifyConnection
or VerifyPeerCertificate". LLMs almost never add the verify callback,
so the resulting code is wide open.

What this flags
---------------
* ``InsecureSkipVerify: true`` (struct literal field, any whitespace).
* ``InsecureSkipVerify = true`` (field assignment on an existing
  ``tls.Config`` value).
* ``InsecureSkipVerify : true`` (rare YAML-style spacing).
* The boolean must be the literal ``true`` — a variable like
  ``InsecureSkipVerify: skipVerify`` is not flagged.

What this does NOT flag
-----------------------
* ``InsecureSkipVerify: false`` — explicit-safe.
* The field name appearing inside a string literal or after a ``//``
  line comment (handled by a Go-aware line stripper).
* Lines suffixed with ``// insecureskipverify-ok``.
* Test files (``*_test.go``). TLS short-circuiting in tests is common
  and lower-risk; opt back in by passing the file explicitly.

Usage
-----
    python3 detect.py <file_or_dir> [...]

Exit 1 if any findings, 0 otherwise. python3 stdlib only.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

SUPPRESS = "// insecureskipverify-ok"

# Match ``InsecureSkipVerify`` followed by ``:`` or ``=``, optional
# whitespace, then the literal ``true`` ending at a non-word boundary.
RE_INSECURE = re.compile(
    r"\bInsecureSkipVerify\s*[:=]\s*true\b"
)


def _strip_strings_and_comments(line: str) -> str:
    """Replace string-literal contents with spaces; drop ``//`` line comments.

    Go-flavoured: handles ``"..."`` interpreted strings, ``\\``-escapes,
    raw ```...``` strings, and ``'.'`` rune literals. Does not track
    ``/* ... */`` block comments across lines.
    """
    out: list[str] = []
    i = 0
    n = len(line)
    in_s = False  # interpreted string
    in_r = False  # rune
    in_raw = False  # raw string (backtick)
    while i < n:
        ch = line[i]
        if in_raw:
            if ch == "`":
                in_raw = False
                out.append("`")
            else:
                out.append(" ")
        elif in_s:
            if ch == "\\" and i + 1 < n:
                out.append("  ")
                i += 2
                continue
            if ch == '"':
                in_s = False
                out.append('"')
            else:
                out.append(" ")
        elif in_r:
            if ch == "\\" and i + 1 < n:
                out.append("  ")
                i += 2
                continue
            if ch == "'":
                in_r = False
                out.append("'")
            else:
                out.append(" ")
        else:
            if ch == "/" and i + 1 < n and line[i + 1] == "/":
                break
            if ch == '"':
                in_s = True
                out.append('"')
            elif ch == "'":
                in_r = True
                out.append("'")
            elif ch == "`":
                in_raw = True
                out.append("`")
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
        stripped = _strip_strings_and_comments(raw)
        if RE_INSECURE.search(stripped):
            findings.append(
                (path, lineno, "tls-insecure-skip-verify", raw.rstrip())
            )
    return findings


def iter_paths(args: list[str]) -> list[Path]:
    out: list[Path] = []
    for a in args:
        p = Path(a)
        if p.is_file():
            out.append(p)
        elif p.is_dir():
            for sub in sorted(p.rglob("*.go")):
                if sub.name.endswith("_test.go"):
                    continue
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
