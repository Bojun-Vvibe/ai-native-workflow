"""Worked example for request-coalescer.

Three scenarios:
  1. 8 threads concurrently call expand_user(user_id=42); leader runs
     once, 7 followers attach, all see the same result.
  2. Leader raises; all followers see the same exception (not a stale
     result, not None).
  3. Sequential calls (no concurrency) DO each fire upstream — the
     coalescer is in-flight only, not a cache.
  4. Calling without safe_for_coalescing=True raises CoalescerError.
"""

from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from coalescer import CoalescerError, RequestCoalescer


# Counters live at module scope so worker threads can mutate them
# without going through a queue.
upstream_calls = {"expand_user": 0, "raises": 0}


def expand_user(user_id: int) -> dict:
    upstream_calls["expand_user"] += 1
    # Simulate a 50ms upstream latency so every follower has time to
    # attach to the in-flight slot before the leader returns.
    time.sleep(0.05)
    return {"user_id": user_id, "name": f"User-{user_id}", "tier": "gold"}


def always_raises(user_id: int) -> dict:
    upstream_calls["raises"] += 1
    time.sleep(0.05)
    raise RuntimeError(f"upstream is down (user_id={user_id})")


def key_by_user(user_id: int) -> tuple:
    return ("expand_user", user_id)


def scenario_1():
    print("Scenario 1: 8 concurrent expand_user(42) → 1 upstream call")
    print("-" * 70)
    upstream_calls["expand_user"] = 0
    coalescer = RequestCoalescer(key_fn=key_by_user, safe_for_coalescing=True)
    results = [None] * 8
    threads = []

    def worker(i):
        results[i] = coalescer.call(expand_user, user_id=42)

    for i in range(8):
        t = threading.Thread(target=worker, args=(i,))
        threads.append(t)
        t.start()
    for t in threads:
        t.join()

    distinct = {id(r) for r in results}
    print(f"  upstream_calls['expand_user'] = {upstream_calls['expand_user']}")
    print(f"  distinct result objects        = {len(distinct)}")
    print(f"  sample result                  = {results[0]}")
    print(f"  coalescer.state()              = {coalescer.state()}")


def scenario_2():
    print()
    print("Scenario 2: leader raises → all 5 followers see the same exception")
    print("-" * 70)
    upstream_calls["raises"] = 0
    coalescer = RequestCoalescer(key_fn=key_by_user, safe_for_coalescing=True)
    errors = [None] * 5
    threads = []

    def worker(i):
        try:
            coalescer.call(always_raises, user_id=99)
        except BaseException as e:  # noqa: BLE001
            errors[i] = repr(e)

    for i in range(5):
        t = threading.Thread(target=worker, args=(i,))
        threads.append(t)
        t.start()
    for t in threads:
        t.join()

    print(f"  upstream_calls['raises']       = {upstream_calls['raises']}")
    print(f"  distinct error reprs           = {len(set(errors))}")
    print(f"  sample error                   = {errors[0]}")
    print(f"  coalescer.state()              = {coalescer.state()}")


def scenario_3():
    print()
    print("Scenario 3: 3 SEQUENTIAL calls → 3 upstream calls (not a cache)")
    print("-" * 70)
    upstream_calls["expand_user"] = 0
    coalescer = RequestCoalescer(key_fn=key_by_user, safe_for_coalescing=True)
    for _ in range(3):
        coalescer.call(expand_user, user_id=7)
    print(f"  upstream_calls['expand_user'] = {upstream_calls['expand_user']}")
    print(f"  coalescer.state()              = {coalescer.state()}")


def scenario_4():
    print()
    print("Scenario 4: missing safe_for_coalescing=True → CoalescerError")
    print("-" * 70)
    coalescer = RequestCoalescer(key_fn=key_by_user)
    try:
        coalescer.call(expand_user, user_id=1)
    except CoalescerError as e:
        print(f"  raised: CoalescerError({str(e)!r})")


if __name__ == "__main__":
    scenario_1()
    scenario_2()
    scenario_3()
    scenario_4()
