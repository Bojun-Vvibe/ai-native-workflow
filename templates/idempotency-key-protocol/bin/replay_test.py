"""Deterministic harness exercising the three legal transitions.

Run:
    python3 replay_test.py <store_path>

Prints one line per transition; exits 0 on success.
"""

from __future__ import annotations

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from idempotency_store import IdempotencyConflict, IdempotencyStore  # noqa: E402


def main() -> int:
    # Injected fake clock — strictly monotonic, deterministic.
    ticks = iter([1_700_000_000.0 + i for i in range(100)])
    clock = lambda: next(ticks)  # noqa: E731

    store_path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        tempfile.mkdtemp(prefix="idem-"), "store.json"
    )
    if os.path.exists(store_path):
        os.remove(store_path)

    store = IdempotencyStore(path=store_path, clock=clock)

    # Side-effect counter: how many times the underlying tool ran.
    calls = {"n": 0}

    def post_comment(req):
        calls["n"] += 1
        return {"comment_id": f"c-{calls['n']}", "body": req["body"]}

    key = "agent-A:m-1:s-3:post_comment:op-xyz"
    body = {"pr": 42, "body": "looks good"}

    # Transition 1: fresh
    r1 = store.call(key, body, post_comment, ttl_seconds=3600)
    print(f"transition=fresh status={r1['status']} side_effects={calls['n']} comment_id={r1['response']['comment_id']}")

    # Transition 2: replay (same key, same body)
    r2 = store.call(key, body, post_comment, ttl_seconds=3600)
    print(f"transition=replay status={r2['status']} side_effects={calls['n']} comment_id={r2['response']['comment_id']}")

    # Transition 2 again to prove unbounded replay safety
    r3 = store.call(key, body, post_comment, ttl_seconds=3600)
    print(f"transition=replay status={r3['status']} side_effects={calls['n']} comment_id={r3['response']['comment_id']}")

    # Transition 3: conflict (same key, different body)
    bad_body = {"pr": 42, "body": "DIFFERENT"}
    try:
        store.call(key, bad_body, post_comment, ttl_seconds=3600)
        print("transition=conflict status=UNEXPECTED_OK")
        return 1
    except IdempotencyConflict as exc:
        d = exc.detail
        print(
            f"transition=conflict status=raised side_effects={calls['n']} "
            f"expected={d['expected_request_hash'][:12]} received={d['received_request_hash'][:12]}"
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
