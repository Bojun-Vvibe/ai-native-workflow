"""Worked example for tool-result-cache.

Two scenarios:
  1. Deterministic tool (sha256_of_file) — second call hits cache,
     volatile request_id ignored via identity_fields.
  2. Non-deterministic tool (read_clock) — write is refused with
     UnsafeCacheError; cache stays empty.
  3. Per-entry TTL — entry written with ttl_s=5 expires after the
     fake clock advances past it.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from cache import ToolResultCache, UnsafeCacheError, cache_key


class FakeClock:
    def __init__(self, t: float) -> None:
        self.t = t

    def __call__(self) -> float:
        return self.t


def main() -> None:
    clock = FakeClock(1000.0)
    cache = ToolResultCache(
        safe_tools=frozenset({"sha256_of_file", "read_file"}),
        now_fn=clock,
    )

    print("== part 1: deterministic tool, identity_fields filters volatile metadata ==")
    args_a = {"path": "/srv/data/spec.md", "request_id": "req-001"}
    args_b = {"request_id": "req-002", "path": "/srv/data/spec.md"}  # different order, different request_id
    args_c = {"path": "/srv/data/other.md", "request_id": "req-003"}

    k_a = cache_key("sha256_of_file", args_a, identity_fields=["path"])
    k_b = cache_key("sha256_of_file", args_b, identity_fields=["path"])
    k_c = cache_key("sha256_of_file", args_c, identity_fields=["path"])
    print(f"key(args_a) == key(args_b)? {k_a == k_b}  (volatile request_id ignored)")
    print(f"key(args_a) == key(args_c)? {k_a == k_c}  (path differs -> different key)")

    # call A: miss, then write
    hit = cache.lookup(k_a)
    assert hit is None
    print(f"call-A lookup: miss; executing tool, writing result")
    cache.write(
        "sha256_of_file",
        k_a,
        result={"sha256": "abc123" * 10 + "deadbe", "bytes": 4096},
        ttl_s=60.0,
        source_call_id="call-A",
    )

    # call B: hit
    clock.t = 1000.05
    hit = cache.lookup(k_b)
    assert hit is not None
    print(f"call-B lookup (volatile-only diff): HIT source_call_id={hit['source_call_id']} "
          f"written_at={hit['written_at']:.2f}")
    print(f"           result.bytes={hit['result']['bytes']}")

    print()
    print("== part 2: non-deterministic tool refuses to cache ==")
    args_d = {"tz": "UTC"}
    k_d = cache_key("read_clock", args_d)
    try:
        cache.write("read_clock", k_d, result={"now": 1234567890}, ttl_s=10.0, source_call_id="call-D")
    except UnsafeCacheError as e:
        print(f"UnsafeCacheError raised as expected: {e}")

    print()
    print("== part 3: per-entry TTL expires ==")
    cache.write(
        "read_file",
        cache_key("read_file", {"path": "/etc/short-lived.txt"}),
        result={"text": "hello", "bytes": 5},
        ttl_s=5.0,
        source_call_id="call-E",
    )
    k_e = cache_key("read_file", {"path": "/etc/short-lived.txt"})
    clock.t = 1000.05 + 4.9  # still within ttl
    hit = cache.lookup(k_e)
    print(f"lookup at t={clock.t:.2f} (within ttl): {'HIT' if hit else 'miss'}")
    clock.t = 1000.05 + 5.5  # past ttl
    hit = cache.lookup(k_e)
    print(f"lookup at t={clock.t:.2f} (past ttl):   {'HIT' if hit else 'miss (evicted)'}")

    print()
    state = cache.state()
    print(f"final state: entries={state['entries']} hits={state['hits']} "
          f"misses={state['misses']} evictions={state['evictions']} "
          f"refused_unsafe_writes={state['refused_unsafe_writes']}")
    print(f"safe_tools: {state['safe_tools']}")


if __name__ == "__main__":
    main()
