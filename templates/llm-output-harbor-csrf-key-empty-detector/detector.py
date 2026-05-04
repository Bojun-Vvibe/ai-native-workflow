#!/usr/bin/env python3
"""Detect Harbor (container registry) ``harbor.yml`` configs that ship
with an empty / placeholder / weak ``csrf_key``.

Harbor's core API protects state-changing requests with a CSRF token
keyed on ``csrf_key``. If that key is empty, set to a placeholder, or
shorter than 32 ASCII characters, the CSRF protection is effectively
defeated and any logged-in admin browsing an attacker-controlled page
can be coerced into creating users, replication policies, etc.

Exit code is the count of files with at least one finding (capped at
255). Stdout lines have the form ``<file>:<line>:<reason>``.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Iterable, List, Tuple

SUPPRESS = re.compile(r"#\s*harbor-csrf-key-allowed")

# top-level key match (no leading whitespace -> top-level mapping entry)
CSRF_KEY_RE = re.compile(r"^csrf_key\s*:\s*(.*?)\s*(?:#.*)?$")

PLACEHOLDERS = {
    "",
    "changeme",
    "change-me",
    "changeit",
    "placeholder",
    "todo",
    "secret",
    "harbor",
    "harborcsrfkey",
    "0123456789abcdef",
}


def _strip_quotes(v: str) -> str:
    v = v.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in ("'", '"'):
        return v[1:-1]
    return v


def _is_weak(value: str) -> Tuple[bool, str]:
    raw = _strip_quotes(value)
    if raw == "":
        return True, "csrf_key is empty"
    low = raw.lower()
    if low in PLACEHOLDERS:
        return True, f"csrf_key is a placeholder value ({raw!r})"
    # env-var style unresolved placeholder
    if raw.startswith("${") and raw.endswith("}"):
        return True, f"csrf_key is an unresolved env placeholder ({raw!r})"
    if len(raw) < 32:
        return True, (
            f"csrf_key is only {len(raw)} chars; Harbor requires >=32 "
            "for adequate entropy"
        )
    # all-same-character
    if len(set(raw)) <= 2:
        return True, f"csrf_key has very low character diversity ({raw!r})"
    return False, ""


def scan(source: str) -> List[Tuple[int, str]]:
    findings: List[Tuple[int, str]] = []
    if SUPPRESS.search(source):
        return findings

    saw_key = False
    for i, raw in enumerate(source.splitlines(), start=1):
        # only top-level: must start at column 0
        if raw.startswith(" ") or raw.startswith("\t"):
            continue
        m = CSRF_KEY_RE.match(raw)
        if not m:
            continue
        saw_key = True
        value = m.group(1)
        bad, reason = _is_weak(value)
        if bad:
            findings.append((i, reason))

    # If file is clearly a harbor.yml (contains hostname + harbor_admin_password
    # for example) but csrf_key is missing entirely, that is also a finding.
    if not saw_key:
        looks_like_harbor = (
            re.search(r"^harbor_admin_password\s*:", source, re.MULTILINE)
            or re.search(r"^hostname\s*:", source, re.MULTILINE)
            and re.search(r"^http\s*:", source, re.MULTILINE)
        )
        if looks_like_harbor:
            findings.append((1, "harbor.yml has no csrf_key set at all"))

    return findings


def scan_paths(paths: Iterable[Path]) -> int:
    bad_files = 0
    targets: List[Path] = []
    for path in paths:
        if path.is_dir():
            for ext in ("harbor.yml", "harbor.yaml", "*.yml", "*.yaml"):
                targets.extend(sorted(path.rglob(ext)))
        else:
            targets.append(path)
    seen = set()
    for f in targets:
        if f in seen:
            continue
        seen.add(f)
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
