#!/usr/bin/env python3
"""detector.py — flag Drone CI configs that ship a weak / placeholder
``DRONE_RPC_SECRET``.

The secret is a shared HMAC key between the Drone server and every
runner. A weak value lets anyone who can reach the server impersonate a
runner, register pipelines, and exfiltrate secrets.

Bad patterns:
  R1: ``DRONE_RPC_SECRET=<weak>`` where weak ∈ {short, dictionary, demo
      placeholder} — env / compose / Dockerfile form.
  R2: ``DRONE_RPC_SECRET`` and ``DRONE_RUNNER_SECRET`` (or
      ``DRONE_AGENT_SECRET``) literally identical to a docs-copy value
      such as ``superdupersecret`` / ``changeme`` / ``secret``.
  R3: Same secret expanded inline twice with the same weak literal in
      one compose file (server + runner sections both pinned to the
      placeholder).

Exit 0 iff every bad sample matches and zero good samples match.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

# Common docs / tutorial placeholder values that make it into LLM output.
_PLACEHOLDERS = {
    "secret",
    "secret123",
    "changeme",
    "change-me",
    "changeit",
    "password",
    "drone",
    "dronesecret",
    "drone-secret",
    "dronerpc",
    "demo",
    "example",
    "test",
    "testing",
    "placeholder",
    "superdupersecret",
    "supersecret",
    "rpcsecret",
    "rpc-secret",
    "abc123",
    "12345678",
    "1234567890",
    "0000000000",
    "aaaaaaaa",
    "topsecret",
    "mysecret",
    "your-secret-here",
    "your_secret_here",
    "yoursecret",
    "insertsecret",
    "todo",
    "tbd",
}

# Shannon-ish heuristic: anything < 24 chars or with very low character
# diversity is treated as weak. The Drone docs explicitly recommend
# `openssl rand -hex 16` (32 chars).
_MIN_LEN = 24
_MIN_UNIQUE = 8

_SECRET_KEYS = (
    "DRONE_RPC_SECRET",
    "DRONE_AGENT_SECRET",
    "DRONE_RUNNER_SECRET",
)

# Match KEY=VAL or KEY: VAL (compose / k8s / env file). Stops at whitespace,
# quote, comment, or end of line. Strips one layer of quoting.
_KV = re.compile(
    r'(?P<k>DRONE_(?:RPC|AGENT|RUNNER)_SECRET)\s*[:=]\s*'
    r'(?P<q>["\']?)(?P<v>[^"\'\s#]+)(?P=q)'
)


def _is_weak(value: str) -> bool:
    v = value.strip()
    if not v:
        return True
    low = v.lower()
    if low in _PLACEHOLDERS:
        return True
    if len(v) < _MIN_LEN:
        return True
    if len(set(v)) < _MIN_UNIQUE:
        return True
    # Repeating short pattern e.g. abcabcabcabc
    if len(v) >= 6 and len(set(v[: len(v) // 2])) <= 3:
        # also catches "secretsecretsecret..."
        if v[: len(v) // 2] == v[len(v) // 2 : 2 * (len(v) // 2)]:
            return True
    # Pure decimal / hex of obvious low entropy (e.g. 1111111111111111)
    if re.fullmatch(r'(.)\1{7,}', v):
        return True
    return False


def is_bad(path: Path) -> bool:
    text = path.read_text(errors="replace")

    weak_hits: list[tuple[str, str]] = []
    for m in _KV.finditer(text):
        # Skip env-var passthrough like `DRONE_RPC_SECRET=${DRONE_RPC_SECRET}`
        # or `${DRONE_RPC_SECRET:?required}`. These are not literal weak
        # values; the actual secret comes from the host environment.
        val = m.group("v")
        if val.startswith("$"):
            continue
        if _is_weak(val):
            weak_hits.append((m.group("k"), val))

    if not weak_hits:
        return False

    # R1: any single weak literal is bad.
    return True


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
