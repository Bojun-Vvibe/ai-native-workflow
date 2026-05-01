#!/usr/bin/env python3
"""Detect Access-Control-Allow-Origin: * combined with Allow-Credentials: true.

Walks a directory, reads each regular file as UTF-8 (errors='replace'),
and within a sliding 12-line window flags co-occurrence of a wildcard
origin and a credentials-enabled directive. Also flags single-call
framework shorthands that bundle both in one expression.

Exit code:
  0 — no findings
  1 — at least one finding (or unreadable target)

Output format:
  <path>:<line>: cors-wildcard-with-credentials: <reason>

Suppression: append "# cors-ok" or "// cors-ok" to any line inside the
window to suppress the entire window's finding.

Pure stdlib; no third-party deps.
"""

from __future__ import annotations

import os
import re
import sys
from typing import Iterable, List, Tuple

WINDOW = 12

# Wildcard-origin patterns (header-form, code-form, config-form).
# We require the literal star "*" as the value.
WILDCARD_ORIGIN_PATTERNS: List[re.Pattern] = [
    # Raw header line: "Access-Control-Allow-Origin: *"
    re.compile(r"Access-Control-Allow-Origin\s*:\s*\*"),
    # nginx / Apache: add_header / Header set ... "*"
    re.compile(r"""(?ix)
        (?:add_header|Header\s+set|Header\s+always\s+set)\s+
        Access-Control-Allow-Origin\s+
        ['"]?\*['"]?
    """),
    # Code: anywhere we see the header name as a string immediately
    # paired (within a few chars) with the star value.
    # e.g. setHeader("Access-Control-Allow-Origin", "*"),
    #      headers["Access-Control-Allow-Origin"] = "*"
    #      .header("Access-Control-Allow-Origin", "*")
    re.compile(r"""(?x)
        ['"]Access-Control-Allow-Origin['"]
        \s*[,:=]\s*
        ['"]\*['"]
    """),
]

# Credentials-enabled patterns.
CREDENTIALS_TRUE_PATTERNS: List[re.Pattern] = [
    re.compile(r"Access-Control-Allow-Credentials\s*:\s*true", re.IGNORECASE),
    re.compile(r"""(?ix)
        (?:add_header|Header\s+set|Header\s+always\s+set)\s+
        Access-Control-Allow-Credentials\s+
        ['"]?true['"]?
    """),
    re.compile(r"""(?x)
        ['"]Access-Control-Allow-Credentials['"]
        \s*[,:=]\s*
        ['"]?(?:true|True)['"]?
    """),
]

# Single-call framework shorthands that bundle both in one expression.
# Each is matched on a single line and reported directly (no window needed).
SHORTHAND_PATTERNS: List[Tuple[re.Pattern, str]] = [
    # Express cors(): cors({ origin: "*", credentials: true })
    # or origin: true (reflects every origin) + credentials: true.
    (
        re.compile(
            r"""(?x)
            \bcors\s*\(\s*\{[^}]*
            origin\s*:\s*(?:['"]\*['"]|true)
            [^}]*
            credentials\s*:\s*true
            [^}]*\}
            """,
            re.IGNORECASE | re.DOTALL,
        ),
        "express-cors-wildcard-with-credentials",
    ),
    (
        re.compile(
            r"""(?x)
            \bcors\s*\(\s*\{[^}]*
            credentials\s*:\s*true
            [^}]*
            origin\s*:\s*(?:['"]\*['"]|true)
            [^}]*\}
            """,
            re.IGNORECASE | re.DOTALL,
        ),
        "express-cors-wildcard-with-credentials",
    ),
    # FastAPI / Starlette CORSMiddleware(allow_origins=["*"], allow_credentials=True)
    (
        re.compile(
            r"""(?x)
            CORSMiddleware\s*\([^)]*
            allow_origins\s*=\s*\[[^\]]*['"]\*['"][^\]]*\]
            [^)]*
            allow_credentials\s*=\s*True
            """,
            re.DOTALL,
        ),
        "fastapi-cors-wildcard-with-credentials",
    ),
    (
        re.compile(
            r"""(?x)
            CORSMiddleware\s*\([^)]*
            allow_credentials\s*=\s*True
            [^)]*
            allow_origins\s*=\s*\[[^\]]*['"]\*['"][^\]]*\]
            """,
            re.DOTALL,
        ),
        "fastapi-cors-wildcard-with-credentials",
    ),
    # Flask-CORS: CORS(app, origins="*", supports_credentials=True)
    (
        re.compile(
            r"""(?x)
            \bCORS\s*\([^)]*
            origins\s*=\s*['"]\*['"]
            [^)]*
            supports_credentials\s*=\s*True
            """,
            re.DOTALL,
        ),
        "flask-cors-wildcard-with-credentials",
    ),
    (
        re.compile(
            r"""(?x)
            \bCORS\s*\([^)]*
            supports_credentials\s*=\s*True
            [^)]*
            origins\s*=\s*['"]\*['"]
            """,
            re.DOTALL,
        ),
        "flask-cors-wildcard-with-credentials",
    ),
]

SUPPRESS_RE = re.compile(r"(?:#|//)\s*cors-ok\b")

# Skip very large or clearly binary files.
SKIP_EXT = {".png", ".jpg", ".jpeg", ".gif", ".pdf", ".zip", ".tar",
            ".gz", ".bz2", ".xz", ".7z", ".class", ".jar", ".so",
            ".dylib", ".o", ".a", ".bin", ".woff", ".woff2", ".ttf",
            ".otf", ".ico", ".mp3", ".mp4", ".mov", ".webp"}
MAX_BYTES = 2 * 1024 * 1024


def _is_skippable(path: str) -> bool:
    base = os.path.basename(path)
    if base.startswith("."):
        # Allow hidden text files like .htaccess explicitly.
        if base.lower() not in {".htaccess", ".htpasswd"}:
            return True
    _, ext = os.path.splitext(path)
    if ext.lower() in SKIP_EXT:
        return True
    try:
        if os.path.getsize(path) > MAX_BYTES:
            return True
    except OSError:
        return True
    return False


def _read_lines(path: str) -> List[str] | None:
    try:
        with open(path, "rb") as f:
            data = f.read()
    except OSError:
        return None
    if b"\x00" in data[:1024]:
        return None
    text = data.decode("utf-8", errors="replace")
    return text.splitlines()


def _line_has_origin_wildcard(line: str) -> bool:
    return any(p.search(line) for p in WILDCARD_ORIGIN_PATTERNS)


def _line_has_credentials_true(line: str) -> bool:
    return any(p.search(line) for p in CREDENTIALS_TRUE_PATTERNS)


def _scan_file(path: str) -> List[Tuple[str, int, str]]:
    """Return list of (path, line_no, reason) findings."""
    lines = _read_lines(path)
    if lines is None:
        return []

    findings: List[Tuple[str, int, str]] = []

    # Pass 1: shorthand single-call patterns (also try a 3-line glued
    # window so we catch reasonable line wrapping).
    for idx, line in enumerate(lines):
        if SUPPRESS_RE.search(line):
            continue
        # Single-line check.
        for pat, label in SHORTHAND_PATTERNS:
            if pat.search(line):
                findings.append((path, idx + 1, label))
                break
        else:
            # 3-line glued check for wrapped calls.
            if idx + 2 < len(lines):
                glued = line + " " + lines[idx + 1] + " " + lines[idx + 2]
                if SUPPRESS_RE.search(lines[idx + 1]) or SUPPRESS_RE.search(lines[idx + 2]):
                    continue
                for pat, label in SHORTHAND_PATTERNS:
                    if pat.search(glued):
                        findings.append((path, idx + 1, label + "-multiline"))
                        break

    # Pass 2: header / config co-occurrence in a sliding window.
    origin_lines: List[int] = []
    cred_lines: List[int] = []
    for idx, line in enumerate(lines):
        if _line_has_origin_wildcard(line):
            origin_lines.append(idx)
        if _line_has_credentials_true(line):
            cred_lines.append(idx)

    reported_pairs: set = set()
    for o in origin_lines:
        for c in cred_lines:
            if abs(o - c) <= WINDOW:
                lo = min(o, c)
                hi = max(o, c)
                # Suppression: if any line in the window has cors-ok, skip.
                window_lines = lines[lo:hi + 1]
                if any(SUPPRESS_RE.search(wl) for wl in window_lines):
                    continue
                key = (lo, hi)
                if key in reported_pairs:
                    continue
                reported_pairs.add(key)
                findings.append(
                    (path, lo + 1,
                     f"header-cooccurrence (origin@{o + 1},credentials@{c + 1})")
                )

    return findings


def _walk(target: str) -> Iterable[str]:
    if os.path.isfile(target):
        yield target
        return
    for root, dirs, files in os.walk(target):
        # Skip VCS / vendored noise.
        dirs[:] = [d for d in dirs if d not in {".git", "node_modules",
                                                "__pycache__", ".venv",
                                                "venv", "dist", "build"}]
        for name in files:
            yield os.path.join(root, name)


def main(argv: List[str]) -> int:
    if len(argv) != 2:
        print(f"usage: {argv[0]} <path>", file=sys.stderr)
        return 2
    target = argv[1]
    if not os.path.exists(target):
        print(f"{argv[0]}: no such path: {target}", file=sys.stderr)
        return 2

    findings: List[Tuple[str, int, str]] = []
    for path in _walk(target):
        if _is_skippable(path):
            continue
        findings.extend(_scan_file(path))

    findings.sort(key=lambda t: (t[0], t[1]))
    for path, line, reason in findings:
        print(f"{path}:{line}: cors-wildcard-with-credentials: {reason}")

    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
