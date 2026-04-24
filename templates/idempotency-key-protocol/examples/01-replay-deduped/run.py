"""Worked example 01: a tool call retried 3× runs once."""

from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "bin"))

from idempotency_store import IdempotencyStore  # noqa: E402


def main() -> int:
    ticks = iter([1_700_000_000.0 + i * 0.5 for i in range(20)])
    clock = lambda: next(ticks)  # noqa: E731

    store_path = os.path.join(HERE, "store.json")
    if os.path.exists(store_path):
        os.remove(store_path)

    store = IdempotencyStore(path=store_path, clock=clock)
    branches_created = []

    def create_branch(req):
        branches_created.append(req["name"])
        return {"branch": req["name"], "sha": "deadbeef"}

    key = "agent-A:m-7:s-2:create_branch:fix-cache"
    body = {"repo": "vvibe", "name": "fix/cache-eviction"}

    print("# Three retries with the same key + body:")
    for attempt in (1, 2, 3):
        env = store.call(key, body, create_branch, ttl_seconds=600)
        print(f"attempt={attempt} status={env['status']} branch={env['response']['branch']}")

    print(f"# Underlying side effect ran {len(branches_created)} time(s): {branches_created}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
