#!/usr/bin/env python3
"""detector.py — flag vsftpd configs that enable anonymous FTP, especially
with write/upload/mkdir permissions.

Exit 0 iff every bad sample matches and zero good samples match.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

# Match `key=value` ignoring leading whitespace, treating commented lines as
# absent. vsftpd directives are case-sensitive (lowercase) and the value
# tokens are usually YES/NO (uppercase) — but be tolerant of spacing and
# quotes that LLMs sometimes emit.
def _directive(text: str, key: str) -> str | None:
    pat = re.compile(
        rf'^[ \t]*{re.escape(key)}[ \t]*=[ \t]*["\']?([A-Za-z]+)["\']?[ \t]*(?:#.*)?$',
        re.MULTILINE,
    )
    m = None
    for m in pat.finditer(text):
        pass  # keep last (later directive wins in vsftpd)
    return m.group(1).upper() if m else None


def _yes(text: str, key: str) -> bool:
    return _directive(text, key) == "YES"


# Dockerfile RUN/echo lines like:  echo "anonymous_enable=YES" >> /etc/vsftpd.conf
_DOCKER_BAKE = re.compile(
    r'(echo|printf)[^\n]*["\']anonymous_enable[ \t]*=[ \t]*YES["\'][^\n]*>>?[ \t]*[^\n]*vsftpd',
    re.IGNORECASE,
)


def is_bad(path: Path) -> bool:
    text = path.read_text(errors="replace")

    anon_on = _yes(text, "anonymous_enable")

    # R1: anon + any anon write directive
    if anon_on and (
        _yes(text, "anon_upload_enable")
        or _yes(text, "anon_mkdir_write_enable")
        or _yes(text, "anon_other_write_enable")
    ):
        return True

    # R2: anon + global write_enable
    if anon_on and _yes(text, "write_enable"):
        return True

    # R3: anon + no_anon_password (silent anonymous, no email prompt)
    if anon_on and _yes(text, "no_anon_password"):
        return True

    # R4: Dockerfile bakes anonymous_enable=YES into a vsftpd config via
    # echo/printf redirection. The directive itself is inside a string, so
    # _directive() won't see it — match the bake line directly.
    if _DOCKER_BAKE.search(text):
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
