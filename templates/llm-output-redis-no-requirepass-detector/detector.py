#!/usr/bin/env python3
"""detector.py — flag Redis configs / launch commands that expose the
server with no `requirepass` set, especially when also bound to a public
interface or with `protected-mode no`.

Exit 0 iff every bad sample matches and zero good samples match.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


# `requirepass` directive in redis.conf. Last occurrence wins.
_REQUIREPASS = re.compile(
    r'^[ \t]*requirepass[ \t]+(?:"([^"]*)"|\'([^\']*)\'|(\S+))[ \t]*$',
    re.MULTILINE,
)

# `protected-mode no` — Redis disables the localhost-only safety net.
_PROTECTED_MODE_NO = re.compile(
    r'^[ \t]*protected-mode[ \t]+no\b', re.MULTILINE | re.IGNORECASE
)

# `bind 0.0.0.0` or `bind ::` or empty bind list — exposes Redis broadly.
_BIND_PUBLIC = re.compile(
    r'^[ \t]*bind[ \t]+(?:[^\n#]*\b(?:0\.0\.0\.0|::)\b)', re.MULTILINE
)
_BIND_EMPTY = re.compile(r'^[ \t]*bind[ \t]*$', re.MULTILINE)

# Dockerfile / shell `redis-server` launch with no `--requirepass` flag.
_REDIS_SERVER_CMD = re.compile(r'\bredis-server\b[^\n]*', re.IGNORECASE)
_REQUIREPASS_FLAG = re.compile(r'--requirepass\b', re.IGNORECASE)


def _requirepass_value(text: str) -> str | None:
    last = None
    for m in _REQUIREPASS.finditer(text):
        last = m
    if not last:
        return None
    return next((g for g in last.groups() if g is not None), None)


def is_bad(path: Path) -> bool:
    text = path.read_text(errors="replace")

    # Strip comment-only lines for the directive scan but keep them for
    # the shell-command scan (Dockerfiles use `#` for both).
    name = path.name.lower()
    is_shellish = (
        "dockerfile" in name
        or name.endswith(".sh")
        or name.endswith(".yml")
        or name.endswith(".yaml")
        or "compose" in name
    )

    pw = _requirepass_value(text)
    has_pw = bool(pw) and pw.lower() not in {"", '""', "''"}

    bind_public = bool(_BIND_PUBLIC.search(text)) or bool(_BIND_EMPTY.search(text))
    protected_off = bool(_PROTECTED_MODE_NO.search(text))

    # R1: redis.conf with no requirepass AND bound publicly
    if not has_pw and bind_public and not is_shellish:
        return True

    # R2: redis.conf with no requirepass AND protected-mode disabled
    if not has_pw and protected_off and not is_shellish:
        return True

    # R3: shell / Dockerfile / compose that launches redis-server without
    # --requirepass (and no requirepass directive injected)
    if is_shellish:
        cmds = _REDIS_SERVER_CMD.findall(text)
        if cmds and not has_pw and not any(_REQUIREPASS_FLAG.search(c) for c in cmds):
            return True

    # R4: requirepass present but set to an obviously empty / placeholder
    # value (Redis silently accepts empty string and ignores auth)
    if pw is not None and pw.strip() in {"", "foobared", "changeme", "password"}:
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
