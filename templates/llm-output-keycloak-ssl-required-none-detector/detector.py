#!/usr/bin/env python3
"""Detect Keycloak realm exports / config that set sslRequired to "none".

Keycloak realms have an sslRequired field with three valid values:
  - "external" (default): HTTPS required for non-private IP requests
  - "all": HTTPS required for every request
  - "none": cleartext HTTP accepted from anywhere

"none" disables the realm's transport-security floor, allowing tokens,
credentials, and authorization codes to traverse cleartext links. This
detector flags any structured config (JSON / YAML / shell-style env /
CLI flag dump) that sets sslRequired (or SSL_REQUIRED env equivalents)
to "none".

Usage:
  python3 detector.py <path-to-config-file>
Exit 1 + prints "BAD" when the misconfig is present.
Exit 0 + prints "GOOD" otherwise.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# Match key/value pairs across JSON, YAML, .properties, env exports,
# kcadm.sh CLI flags, and Helm value overrides. We deliberately keep
# the regex permissive on whitespace and quote style but strict on the
# token "none" so that "external" / "all" never trip it.
PATTERNS = [
    # JSON / YAML:    "sslRequired": "none"   |   sslRequired: none
    re.compile(r'["\']?sslRequired["\']?\s*[:=]\s*["\']?none["\']?', re.IGNORECASE),
    # .properties / env:  KEYCLOAK_SSL_REQUIRED=none  |  KC_HTTP_RELATIVE_PATH ignored
    re.compile(r'\b(?:KC|KEYCLOAK)_SSL_REQUIRED\s*=\s*["\']?none["\']?', re.IGNORECASE),
    # kcadm.sh:  -s sslRequired=none   |   --set sslRequired=none
    re.compile(r'(?:-s|--set)\s+sslRequired\s*=\s*["\']?none["\']?', re.IGNORECASE),
    # Helm-style flag:  --set realm.sslRequired=none
    re.compile(r'\.sslRequired\s*=\s*["\']?none["\']?', re.IGNORECASE),
]


def looks_bad(text: str) -> bool:
    # Strip line comments so commented-out examples don't trigger.
    cleaned_lines = []
    for raw in text.splitlines():
        line = raw
        # YAML / shell / properties comment
        if "#" in line:
            # Don't strip inside a quoted string (cheap heuristic).
            if line.count('"') % 2 == 0 and line.count("'") % 2 == 0:
                line = line.split("#", 1)[0]
        # // line comment (some annotated JSON-ish samples)
        if "//" in line:
            line = line.split("//", 1)[0]
        cleaned_lines.append(line)
    cleaned = "\n".join(cleaned_lines)
    return any(p.search(cleaned) for p in PATTERNS)


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: detector.py <config-file>", file=sys.stderr)
        return 2
    path = Path(argv[1])
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if looks_bad(text):
        print("BAD")
        return 1
    print("GOOD")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
