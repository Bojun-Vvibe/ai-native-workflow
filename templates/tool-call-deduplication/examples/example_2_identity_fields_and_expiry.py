"""Example 2: identity_fields + window expiry + float rejection.

Three behaviors:

1. A `request_id` and a `now` field that change on every call would
   defeat dedup if hashed naively. `identity_fields=["query","limit"]`
   restricts the hash to the parts that actually determine the
   result, so duplicate logical queries hit cache.

2. After the dedup window expires, the next call re-executes (cache
   miss + eviction recorded in state).

3. A float in the identity-args is rejected loudly — silent precision
   loss in cache keys is a correctness trap.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dedup import CanonicalizationError, DedupCache, dedup_key


class FakeClock:
    def __init__(self) -> None:
        self.t = 5000.0

    def __call__(self) -> float:
        return self.t

    def advance(self, s: float) -> None:
        self.t += s


def main() -> int:
    clock = FakeClock()
    cache = DedupCache(window_seconds=10.0, now_fn=clock)

    # --- 1. identity_fields filters out volatile metadata --------------
    print("== part 1: identity_fields filters out volatile metadata ==")
    identity = ["query", "limit"]

    args_a = {
        "query": "open issues label:bug",
        "limit": 25,
        "request_id": "req-aaa",
        "now": "2026-04-25T10:00:00Z",
    }
    args_b = {
        "query": "open issues label:bug",
        "limit": 25,
        "request_id": "req-bbb",   # different
        "now":        "2026-04-25T10:00:01Z",  # different
    }
    args_c = {
        "query": "open issues label:bug",
        "limit": 50,               # logically different query
        "request_id": "req-ccc",
        "now": "2026-04-25T10:00:02Z",
    }

    k_a = dedup_key("search_issues", args_a, identity_fields=identity)
    k_b = dedup_key("search_issues", args_b, identity_fields=identity)
    k_c = dedup_key("search_issues", args_c, identity_fields=identity)
    print(f"key(args_a) == key(args_b)? {k_a == k_b}  "
          f"(volatile fields ignored)")
    print(f"key(args_a) == key(args_c)? {k_a == k_c}  "
          f"(limit changed -> different key)")

    d = cache.decide("search_issues", args_a, call_id="call-A",
                     identity_fields=identity)
    print(f"\ncall-A: {d['verdict']}")
    cache.record(d["key"], call_id="call-A",
                 result={"hits": 7, "ids": [101, 102, 103, 104, 105, 106, 107]})

    d = cache.decide("search_issues", args_b, call_id="call-B",
                     identity_fields=identity)
    print(f"call-B (volatile-only diff): {d['verdict']} "
          f"served-from={d['cached']['original_call_id']}")

    # --- 2. window expiry --------------------------------------------
    print()
    print("== part 2: window expiry ==")
    print(f"advancing clock by 11s (window=10s)...")
    clock.advance(11.0)
    d = cache.decide("search_issues", args_a, call_id="call-D",
                     identity_fields=identity)
    print(f"call-D after expiry: {d['verdict']}  (entry was evicted)")
    cache.record(d["key"], call_id="call-D",
                 result={"hits": 8, "ids": [101, 102, 103, 104, 105, 106, 107, 108]})

    # --- 3. float rejection --------------------------------------------
    print()
    print("== part 3: float rejection ==")
    try:
        dedup_key("rank", {"score": 0.875, "id": 42},
                  identity_fields=["score", "id"])
    except CanonicalizationError as e:
        print(f"CanonicalizationError raised as expected: {e}")

    print()
    print(f"final state: {json.dumps(cache.state(), sort_keys=True)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
