"""Worked example for weighted-model-router.

Demonstrates:
  1. Determinism: same route_key + same backend set → same backend.
  2. Weight semantics: a 70/20/10 split lands ~70/20/10 over many keys.
  3. Stickiness under weight edit: bumping bucket B from 20→25 only
     reroutes a small fraction of keys (rendezvous property), nowhere
     near the catastrophic full-reshuffle that modular hashing causes.
  4. Exclusion: an excluded backend never wins, even at high weight.
  5. NoEligibleBackend: excluding everything raises loudly.
"""

from __future__ import annotations

from collections import Counter

from router import Backend, NoEligibleBackend, WeightedRouter


def main() -> None:
    print("=" * 60)
    print("weighted-model-router worked example")
    print("=" * 60)

    r1 = WeightedRouter(
        backends=(
            Backend("model-A", weight=70),
            Backend("model-B", weight=20),
            Backend("model-C", weight=10),
        )
    )

    # 1. Determinism
    print("\n[1] determinism (same key → same backend across calls)")
    for k in ("user-42", "user-99", "session-abc"):
        a = r1.route(k).backend
        b = r1.route(k).backend
        c = r1.route(k).backend
        print(f"  key={k!r:>14}  → {a}  (consistent: {a == b == c})")

    # 2. Weight distribution over 10000 synthetic keys
    print("\n[2] weight distribution over 10,000 synthetic keys")
    counts: Counter[str] = Counter()
    keys = [f"req-{i}" for i in range(10_000)]
    for k in keys:
        counts[r1.route(k).backend] += 1
    total = sum(counts.values())
    for name in ("model-A", "model-B", "model-C"):
        pct = counts[name] / total * 100
        print(f"  {name}: {counts[name]:>5}  ({pct:5.2f}%  target ~"
              f"{ {'model-A':70,'model-B':20,'model-C':10}[name] }%)")

    # 3. Stickiness when one weight is bumped
    print("\n[3] stickiness: bump model-B weight 20 → 25")
    r2 = WeightedRouter(
        backends=(
            Backend("model-A", weight=70),
            Backend("model-B", weight=25),
            Backend("model-C", weight=10),
        )
    )
    moved = sum(1 for k in keys if r1.route(k).backend != r2.route(k).backend)
    print(f"  reshuffled keys: {moved} / {len(keys)}  ({moved/len(keys)*100:.2f}%)")
    print("  (a hash-mod router would reshuffle ~67%; HRW reshuffles only"
          " keys whose top-2 score straddled model-B)")

    # 4. Exclusion
    print("\n[4] exclusion: drain model-A, route 5 sample keys")
    for k in ("user-42", "user-99", "session-abc", "req-7", "req-13"):
        res = r1.route(k, exclude={"model-A"})
        print(f"  key={k!r:>14}  → {res.backend}  considered={res.considered}"
              f" excluded={res.excluded}")

    # 5. NoEligibleBackend
    print("\n[5] excluding everything raises NoEligibleBackend")
    try:
        r1.route("user-42", exclude={"model-A", "model-B", "model-C"})
        print("  FAIL: did not raise")
    except NoEligibleBackend as e:
        print(f"  OK: {type(e).__name__}: {e}")

    print("\n" + "=" * 60)
    print("done")


if __name__ == "__main__":
    main()
