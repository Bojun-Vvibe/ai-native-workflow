"""Example 1: agent loops and re-issues the same tool call.

Simulates an agent that, confused by a partial trace, re-issues the
exact same `read_file` call 50ms later. The dedup cache returns the
prior result instead of hitting disk twice. Field order in the args
dict differs between the two calls — the canonicalizer normalizes it.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dedup import DedupCache


class FakeClock:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


def fake_read_file(path: str) -> dict:
    # Imagine an expensive disk + parse step.
    return {"path": path, "lines": 142, "sha256": "deadbeef" * 8}


def main() -> int:
    clock = FakeClock()
    cache = DedupCache(window_seconds=60.0, now_fn=clock)

    # First call from the agent.
    args1 = {"path": "/srv/notes/spec.md", "encoding": "utf-8"}
    decision = cache.decide("read_file", args1, call_id="call-001")
    print(f"t={clock.t:.1f} call-001 decision: {decision['verdict']} "
          f"key={decision['key'][:12]}...")
    assert decision["verdict"] == "execute"
    result = fake_read_file(args1["path"])
    cache.record(decision["key"], call_id="call-001", result=result)
    print(f"           executed -> {json.dumps(result, sort_keys=True)}")

    # 50ms later the agent loops and re-issues the same call.
    # Note the dict key order is different — should not matter.
    clock.advance(0.05)
    args2 = {"encoding": "utf-8", "path": "/srv/notes/spec.md"}
    decision = cache.decide("read_file", args2, call_id="call-002")
    print()
    print(f"t={clock.t:.2f} call-002 decision: {decision['verdict']} "
          f"key={decision['key'][:12]}...")
    if decision["verdict"] == "use_cached":
        c = decision["cached"]
        print(f"           served from cache; original_call_id="
              f"{c['original_call_id']} cached_at={c['cached_at']:.2f}")
        print(f"           result={json.dumps(c['result'], sort_keys=True)}")

    # Different path -> different key -> executes.
    args3 = {"path": "/srv/notes/other.md", "encoding": "utf-8"}
    decision = cache.decide("read_file", args3, call_id="call-003")
    print()
    print(f"t={clock.t:.2f} call-003 (different path) decision: "
          f"{decision['verdict']}")

    print()
    print(f"final state: {json.dumps(cache.state(), sort_keys=True)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
