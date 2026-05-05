#!/usr/bin/env python3
"""detector.py — flag Elasticsearch configs / Dockerfiles / compose files
that explicitly disable X-Pack security, leaving the cluster unauthenticated
and (typically) unencrypted.

Exit 0 iff every bad sample matches and zero good samples match.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


# YAML directive: `xpack.security.enabled: false` (any quoting / casing on the
# bool, optional inline comment).
_YAML_KV = re.compile(
    r'^[ \t]*([A-Za-z0-9_.\-]+)[ \t]*:[ \t]*(?:["\']?([A-Za-z]+)["\']?)[ \t]*(?:#.*)?$',
    re.MULTILINE,
)

# `-Expack.security.enabled=false` style java/JVM args, or
# `xpack.security.enabled=false` env / CLI form (compose `environment:`,
# Dockerfile ENV, shell exports).
_FLAG_FALSE = re.compile(
    r'\bxpack\.security\.(?:enabled|http\.ssl\.enabled|transport\.ssl\.enabled)'
    r'[ \t]*=[ \t]*["\']?false["\']?',
    re.IGNORECASE,
)


def _yaml_lookup(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for m in _YAML_KV.finditer(text):
        out[m.group(1).lower()] = m.group(2).lower()
    return out


def is_bad(path: Path) -> bool:
    text = path.read_text(errors="replace")

    yaml = _yaml_lookup(text)

    # R1: explicit `xpack.security.enabled: false` in elasticsearch.yml form.
    if yaml.get("xpack.security.enabled") == "false":
        return True

    # R2: security on but BOTH transport and http SSL turned off — equivalent
    # to "auth without encryption", credentials cross the wire in cleartext.
    if (
        yaml.get("xpack.security.enabled") == "true"
        and yaml.get("xpack.security.http.ssl.enabled") == "false"
        and yaml.get("xpack.security.transport.ssl.enabled") == "false"
    ):
        return True

    # R3: env / CLI / Dockerfile form `xpack.security.enabled=false`
    if _FLAG_FALSE.search(text):
        # Re-check that the flag we matched actually disables `.enabled`
        # (not just .ssl.enabled, which alone is a separate misconfig but
        # we still want to flag that distinct case as bad too — it leaves
        # the wire in cleartext).
        return True

    # R4: discovery.type=single-node combined with security.enabled false in
    # the same compose `environment:` block — common LLM "just get it working
    # locally" footgun that ends up shipped to staging.
    if "discovery.type=single-node" in text.lower() and re.search(
        r'xpack\.security\.enabled[ \t]*[:=][ \t]*["\']?false', text, re.IGNORECASE
    ):
        return True

    return False


def main(argv: list[str]) -> int:
    bad_hits = bad_total = good_hits = good_total = 0
    for arg in argv:
        p = Path(arg)
        parts = p.parts
        kind = None
        if "bad" in parts and "examples" in parts:
            kind = "bad"
            bad_total += 1
        elif "good" in parts and "examples" in parts:
            kind = "good"
            good_total += 1

        flagged = is_bad(p)
        print(f"{'BAD ' if flagged else 'GOOD'} {p}")
        if flagged and kind == "bad":
            bad_hits += 1
        elif flagged and kind == "good":
            good_hits += 1

    status = "PASS" if bad_hits == bad_total and good_hits == 0 else "FAIL"
    print(f"bad={bad_hits}/{bad_total} good={good_hits}/{good_total} {status}")
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
