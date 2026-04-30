#!/usr/bin/env python3
"""Detect wildcard ALLOWED_HOSTS in Django settings emitted by LLMs.

Django's `ALLOWED_HOSTS` setting is the framework's defense against
HTTP Host-header injection attacks (CWE-942: Permissive Cross-domain
Policy with Untrusted Domains; closely related to CWE-20). When set
to ``["*"]``, Django accepts any value of the ``Host`` header, which
enables:

* Password-reset poisoning (links pointing at attacker-controlled hosts).
* Cache poisoning via mismatched Host header.
* SSRF-style routing in misconfigured proxies.
* Defeats virtual-host isolation.

LLMs emit ``ALLOWED_HOSTS = ["*"]`` by reflex when asked to "fix the
DisallowedHost error" because that is the shortest answer on the
public internet. Production code should enumerate hosts explicitly
or read them from environment variables that are validated.

What this flags
---------------
* ``ALLOWED_HOSTS = ["*"]`` / ``= ('*',)`` (any quote style).
* ``ALLOWED_HOSTS = "*"`` (string-form, also accepted by Django).
* ``ALLOWED_HOSTS += ["*"]`` and ``ALLOWED_HOSTS.append("*")``.
* ``ALLOWED_HOSTS.extend(["*"])``.
* Lists containing ``"*"`` alongside other entries
  (``["app.example.com", "*"]``).

What this does NOT flag
-----------------------
* Explicit allowlists: ``ALLOWED_HOSTS = ["app.example.com"]``.
* Empty list ``ALLOWED_HOSTS = []`` (Django default; not a wildcard).
* Environment-driven values: ``ALLOWED_HOSTS = os.environ["HOSTS"].split(",")``.
* Subdomain wildcards Django does NOT treat as full wildcards:
  ``".example.com"`` (this is Django syntax for "any subdomain of
  example.com" — restrictive, not permissive).
* Lines with the trailing suppression marker ``# allowed-hosts-ok``.
* Occurrences inside ``#`` comments or string literals.

Usage
-----
    python3 detect.py <file_or_dir> [...]

Exit 1 if any findings, 0 otherwise. python3 stdlib only.
Recurses directories looking for ``*.py`` files.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

SUPPRESS = "# allowed-hosts-ok"

# `ALLOWED_HOSTS = "*"` (bare string form).
RE_ASSIGN_BARE_STAR = re.compile(
    r"""^\s*ALLOWED_HOSTS\s*(?:\:\s*[^=]+)?=\s*['"]\*['"]\s*(?:#|$)"""
)

# `ALLOWED_HOSTS = [..., "*", ...]` or tuple form.
RE_ASSIGN_LIST_STAR = re.compile(
    r"""^\s*ALLOWED_HOSTS\s*(?:\:\s*[^=]+)?(?:=|\+=)\s*[\[\(][^\]\)]*"""
    r"""['"]\*['"]"""
)

# `ALLOWED_HOSTS.append("*")` / `.extend([..., "*"])` / `.insert(i, "*")`.
RE_APPEND_STAR = re.compile(
    r"""\bALLOWED_HOSTS\.(?:append|insert|extend)\s*\([^)]*['"]\*['"]"""
)


def _strip_comment(line: str) -> str:
    """Drop content after the first `#` that is not inside a string."""
    out = []
    in_s = False
    quote = ""
    i = 0
    while i < len(line):
        ch = line[i]
        if in_s:
            if ch == "\\" and i + 1 < len(line):
                out.append(ch)
                out.append(line[i + 1])
                i += 2
                continue
            if ch == quote:
                in_s = False
            out.append(ch)
        else:
            if ch == "#":
                break
            if ch in ("'", '"'):
                in_s = True
                quote = ch
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
        # Use the raw line for matching ALLOWED_HOSTS = "*", because the
        # suppression check above is the user's escape hatch.
        # We strip comments to avoid matching commented examples.
        stripped = _strip_comment(raw)
        if "ALLOWED_HOSTS" not in stripped:
            continue
        if RE_ASSIGN_BARE_STAR.search(stripped):
            findings.append((path, lineno, "django-allowed-hosts-bare-star", raw.rstrip()))
            continue
        if RE_ASSIGN_LIST_STAR.search(stripped):
            findings.append((path, lineno, "django-allowed-hosts-list-star", raw.rstrip()))
            continue
        if RE_APPEND_STAR.search(stripped):
            findings.append((path, lineno, "django-allowed-hosts-append-star", raw.rstrip()))
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
