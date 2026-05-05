#!/usr/bin/env python3
"""detector.py — flag phpMyAdmin configs that enable
``AllowNoPassword`` for any server entry, letting anyone authenticate
to the wrapped MySQL/MariaDB instance with an empty password.

The default in shipped phpMyAdmin is ``false``. LLMs frequently flip
it to ``true`` while "fixing" a login error against a freshly
``mysql_secure_installation``-skipped database, then ship that config.

Bad patterns:
  R1: PHP config — ``$cfg['Servers'][$i]['AllowNoPassword'] = true;``
  R2: PHP config — ``$cfg['Servers'][$i]['AllowNoPassword'] = TRUE;``
      / ``= 1;`` / any non-zero numeric / ``= "true";``.
  R3: Docker env (compose, Dockerfile ENV, k8s env):
      ``PMA_ALLOW_NO_PASSWORD=1`` (any truthy: 1 / true / TRUE / yes).
  R4: Top-level ``AllowNoPassword: true`` in a YAML helm values file
      under a ``phpmyadmin`` / ``pma`` block.

Exit 0 iff every bad sample matches and zero good samples match.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

_TRUTHY = {"true", "1", "yes", "on"}

# PHP: $cfg['Servers'][$i]['AllowNoPassword'] = <val>;
_PHP_ASSIGN = re.compile(
    r"""\$cfg\s*\[\s*['"]Servers['"]\s*\]\s*\[\s*\$?\w+\s*\]\s*"""
    r"""\[\s*['"]AllowNoPassword['"]\s*\]\s*=\s*"""
    r"""(?P<val>[^;]+?)\s*;""",
    re.IGNORECASE,
)

# Env-style: PMA_ALLOW_NO_PASSWORD=<val>  (also matches `: <val>` in compose).
_ENV_ASSIGN = re.compile(
    r"""\bPMA_ALLOW_NO_PASSWORD\b\s*[:=]\s*['"]?(?P<val>[A-Za-z0-9]+)['"]?""",
    re.IGNORECASE,
)

# YAML: bare `AllowNoPassword: true` (helm values, ansible vars, etc.).
_YAML_ASSIGN = re.compile(
    r"""^[ \t]*AllowNoPassword\s*:\s*['"]?(?P<val>[A-Za-z0-9]+)['"]?""",
    re.IGNORECASE | re.MULTILINE,
)


def _truthy(raw: str) -> bool:
    v = raw.strip().strip("'\"").lower()
    if v in _TRUTHY:
        return True
    # numeric: any non-zero int counts as PHP-truthy
    if v.isdigit() and int(v) != 0:
        return True
    return False


def is_bad(path: Path) -> bool:
    text = path.read_text(errors="replace")

    for m in _PHP_ASSIGN.finditer(text):
        if _truthy(m.group("val")):
            return True

    for m in _ENV_ASSIGN.finditer(text):
        if _truthy(m.group("val")):
            return True

    for m in _YAML_ASSIGN.finditer(text):
        if _truthy(m.group("val")):
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
