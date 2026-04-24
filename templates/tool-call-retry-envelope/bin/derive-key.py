#!/usr/bin/env python3
"""
derive-key.py — host-side semantic-hash key derivation.

Stdlib only. Reads a request envelope on stdin (or from a file arg),
emits the derived `idempotency_key` on stdout. Used by the host's
request handler to compute keys deterministically; also useful in
tests and the worked examples.

Key derivation rule:

    idempotency_key = "tcre_v1_" + sha256_hex(canonical_json({
        "tool":     tool_name,
        "identity": pick(arguments, IDENTITY_FIELDS[tool_name]),
        "scope":    {"tenant": ..., "session": ...}
    }))

Canonical JSON:
  - keys sorted lexicographically at every level
  - no insignificant whitespace
  - UTF-8 encoded for hashing
  - integers serialised as JSON ints, floats as the shortest
    round-tripping decimal (we just use json.dumps default; if your
    args carry floats, normalise them before hashing).
"""

from __future__ import annotations
import argparse
import hashlib
import json
import sys
from typing import Any, Dict, List

# Per-tool allowlist. EVERY tool that wants dedup MUST appear here.
# Editing this map is a wire-contract change; bump the `tcre_v1_`
# prefix if you need to invalidate old keys.
IDENTITY_FIELDS: Dict[str, List[str]] = {
    "email.send":             ["to", "subject_hash", "body_sha256"],
    "stripe.charges.create":  ["customer", "amount", "currency",
                               "metadata.order_id"],
    "git.push":               ["remote_url", "branch", "commit_sha"],
    "db.execute":             ["statement_template", "param_hash"],
    "slack.send":             ["channel", "text_sha256", "thread_ts"],
}


def _canonical_json(obj: Any) -> bytes:
    return json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def _pick(arguments: Dict[str, Any], paths: List[str]) -> Dict[str, Any]:
    """Pluck dotted-path fields out of arguments. Missing → null."""
    out: Dict[str, Any] = {}
    for path in paths:
        cur: Any = arguments
        for part in path.split("."):
            if isinstance(cur, dict) and part in cur:
                cur = cur[part]
            else:
                cur = None
                break
        out[path] = cur
    return out


def derive_key(envelope_request: Dict[str, Any],
               scope: Dict[str, Any]) -> str:
    tool_name = envelope_request["tool_name"]
    if tool_name not in IDENTITY_FIELDS:
        raise ValueError(
            f"tool {tool_name!r} not in IDENTITY_FIELDS; refusing "
            "to derive key. Add it to derive-key.py."
        )
    identity = _pick(envelope_request["arguments"], IDENTITY_FIELDS[tool_name])
    payload = {
        "tool":     tool_name,
        "identity": identity,
        "scope":    scope,
    }
    digest = hashlib.sha256(_canonical_json(payload)).hexdigest()
    return f"tcre_v1_{digest}"


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("file", nargs="?", default="-",
                   help="JSON file containing the request envelope, or - for stdin")
    p.add_argument("--tenant", default="t_default")
    p.add_argument("--session", default="s_default")
    args = p.parse_args()

    data = sys.stdin.read() if args.file == "-" else open(args.file).read()
    req = json.loads(data)
    key = derive_key(req, {"tenant": args.tenant, "session": args.session})
    print(key)
    return 0


if __name__ == "__main__":
    sys.exit(main())
