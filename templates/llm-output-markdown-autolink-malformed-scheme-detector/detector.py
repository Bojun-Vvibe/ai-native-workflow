#!/usr/bin/env python3
"""Detect malformed-scheme autolinks (`<scheme:rest>`) in Markdown.

Stdlib only. Code-fence and inline-code aware.

Usage:
    python3 detector.py FILE [FILE ...]

Exit codes:
    0  clean
    1  malformed autolink found
    2  usage / IO error
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

FENCE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
INLINE_CODE_RE = re.compile(r"`+[^`\n]*`+")
# Candidate <...> token: no whitespace inside, no '=' (skip HTML attrs),
# and at least one ':' inside.
CANDIDATE_RE = re.compile(r"<([^<>\s=]*:[^<>\s]*)>")
SCHEME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.\-]{1,31}$")


def strip_inline_code(line: str) -> str:
    return INLINE_CODE_RE.sub("", line)


def classify(inner: str) -> str | None:
    """Return a human reason if `inner` is a malformed autolink, else None."""
    # `inner` is the text strictly between < and >, guaranteed to contain ':'.
    if inner.startswith("//") or inner.startswith("://"):
        return "missing URI scheme before '//'"
    colon = inner.find(":")
    scheme = inner[:colon]
    rest = inner[colon + 1 :]
    if scheme == "":
        return "empty scheme before ':'"
    if not SCHEME_RE.match(scheme):
        return f"invalid scheme {scheme!r} (expected [A-Za-z][A-Za-z0-9+.-]{{1,31}})"
    # Reject `http::` style double-colons immediately after the scheme.
    if rest.startswith(":"):
        return f"unexpected ':' immediately after scheme {scheme!r}"
    return None


def scan(path: Path) -> list[str]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"{path}: cannot read: {exc}", file=sys.stderr)
        return ["__io__"]

    findings: list[str] = []
    in_fence = False
    fence_marker = ""

    for idx, line in enumerate(text.splitlines(), start=1):
        m = FENCE_RE.match(line)
        if m:
            marker = m.group(1)[0]
            if not in_fence:
                in_fence = True
                fence_marker = marker
            elif marker == fence_marker:
                in_fence = False
                fence_marker = ""
            continue
        if in_fence:
            continue
        scrubbed = strip_inline_code(line)
        for cm in CANDIDATE_RE.finditer(scrubbed):
            inner = cm.group(1)
            reason = classify(inner)
            if reason:
                col = cm.start() + 1
                findings.append(
                    f"{path}:{idx}:{col}: malformed autolink '<{inner}>': {reason}"
                )
    return findings


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: detector.py FILE [FILE ...]", file=sys.stderr)
        return 2
    rc = 0
    for arg in argv[1:]:
        results = scan(Path(arg))
        if results == ["__io__"]:
            rc = max(rc, 2)
            continue
        for line in results:
            print(line)
        if results:
            rc = max(rc, 1)
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv))
