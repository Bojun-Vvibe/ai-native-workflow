"""Worked example for embedding-batch-coalescer.

Three scenarios, real threading, no real network:

1. Burst of 100 concurrent submits -> coalesces into a few size-flushed batches.
2. Trickle (3 items, slow producers) -> flushes by time-window.
3. Heavy duplication -> dedup shrinks upstream items vs submitted.

Run:
    python3 worked_example.py
"""

from __future__ import annotations

import threading
import time
from typing import List, Sequence

from coalescer import EmbeddingBatchCoalescer


def fake_embed(texts: Sequence[str]) -> List[List[float]]:
    # Deterministic, cheap "embedding": [len, sum(ord)%97, count('a')]
    out = []
    for t in texts:
        out.append([float(len(t)), float(sum(ord(c) for c in t) % 97), float(t.count("a"))])
    return out


def scenario_burst() -> None:
    print("== scenario 1: burst of 100 concurrent submits ==")
    c = EmbeddingBatchCoalescer(fake_embed, max_batch_size=32, max_wait_s=0.05)
    futures = []

    def worker(i: int) -> None:
        futures.append(c.submit(f"text-{i}"))

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(100)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    results = [f.result(timeout=2.0) for f in futures]
    c.close(timeout=2.0)

    assert len(results) == 100
    assert all(len(r) == 3 for r in results)
    print(f"  submitted={c.stats.submitted} batches={c.stats.batches_flushed} "
          f"by_size={c.stats.flushed_by_size} by_time={c.stats.flushed_by_time} "
          f"by_close={c.stats.flushed_by_close} upstream_items={c.stats.upstream_items}")
    print(f"  first result: {results[0]}")
    print("  ok")


def scenario_trickle() -> None:
    print("== scenario 2: trickle (3 slow producers) ==")
    c = EmbeddingBatchCoalescer(fake_embed, max_batch_size=32, max_wait_s=0.08)
    futs = []
    for i in range(3):
        futs.append(c.submit(f"slow-{i}"))
        time.sleep(0.01)
    results = [f.result(timeout=2.0) for f in futs]
    c.close(timeout=2.0)
    assert len(results) == 3
    print(f"  submitted={c.stats.submitted} batches={c.stats.batches_flushed} "
          f"by_size={c.stats.flushed_by_size} by_time={c.stats.flushed_by_time} "
          f"by_close={c.stats.flushed_by_close}")
    print("  ok")


def scenario_dedup() -> None:
    print("== scenario 3: heavy duplication ==")
    c = EmbeddingBatchCoalescer(fake_embed, max_batch_size=64, max_wait_s=0.05)
    futs = []
    # 50 submits, only 5 distinct strings
    for i in range(50):
        futs.append(c.submit(f"dup-{i % 5}"))
    results = [f.result(timeout=2.0) for f in futs]
    c.close(timeout=2.0)
    assert len(results) == 50
    # Same input -> same embedding
    grouped = {}
    for i, r in enumerate(results):
        grouped.setdefault(f"dup-{i % 5}", []).append(tuple(r))
    for k, vs in grouped.items():
        assert len(set(vs)) == 1, f"deterministic embed_fn but {k} got drift: {vs}"
    print(f"  submitted={c.stats.submitted} upstream_items={c.stats.upstream_items} "
          f"(dedup ratio: {c.stats.upstream_items}/{c.stats.submitted})")
    print(f"  upstream_calls={c.stats.upstream_calls} batches={c.stats.batches_flushed}")
    print("  ok")


def scenario_error_propagation() -> None:
    print("== scenario 4: upstream error propagates to every future in batch ==")

    def broken_embed(texts):
        raise RuntimeError(f"upstream down (would have embedded {len(texts)})")

    c = EmbeddingBatchCoalescer(broken_embed, max_batch_size=8, max_wait_s=0.02)
    futs = [c.submit(f"x-{i}") for i in range(5)]
    errors = 0
    for f in futs:
        try:
            f.result(timeout=2.0)
        except RuntimeError as e:
            errors += 1
            last = str(e)
    c.close(timeout=2.0)
    assert errors == 5
    print(f"  errors_propagated={errors}/5  msg={last!r}  stats.errors={c.stats.errors}")
    print("  ok")


if __name__ == "__main__":
    scenario_burst()
    scenario_trickle()
    scenario_dedup()
    scenario_error_propagation()
    print("\nAll scenarios passed.")
