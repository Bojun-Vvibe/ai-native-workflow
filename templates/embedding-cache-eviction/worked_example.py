"""End-to-end demo of EmbeddingCache.

Simulates an agent that embeds a stream of text snippets where some
repeat (cache hits), some are novel (misses), and a slow trickle ages
out under TTL pressure.
"""

from __future__ import annotations

import hashlib
from cache import EmbeddingCache


def fake_embed(text: str, dims: int = 4) -> list[float]:
    """Deterministic stand-in for a real embedding model."""
    h = hashlib.sha256(text.encode("utf-8")).digest()
    return [b / 255.0 for b in h[:dims]]


def main() -> None:
    # Fake clock so the demo is reproducible.
    now = [0.0]

    def clock() -> float:
        return now[0]

    cache = EmbeddingCache(max_entries=3, ttl_seconds=10.0, clock=clock)

    stream = [
        ("t=0",  "hello world"),
        ("t=1",  "hello world"),       # hit
        ("t=2",  "agent loop"),
        ("t=3",  "tool call"),
        ("t=4",  "structured output"), # forces LRU eviction of "hello world"
        ("t=5",  "hello world"),       # miss again (was evicted)
        ("t=15", "agent loop"),        # TTL-expired -> miss
        ("t=16", "tool call"),         # also TTL-expired -> miss
        ("t=17", "tool call"),         # hit (just re-inserted)
    ]

    print("step | action | key                   | result")
    print("-----+--------+-----------------------+--------")
    for label, key in stream:
        # Advance fake clock to the stamp embedded in the label.
        now[0] = float(label.split("=", 1)[1])
        cached = cache.get(key)
        if cached is None:
            vec = fake_embed(key)
            cache.put(key, vec)
            result = f"miss -> embed   (len={len(vec)})"
        else:
            result = f"hit  -> reuse   (len={len(cached)})"
        print(f"{label:<5}|        | {key:<22}| {result}")

    print()
    print("final stats:")
    for k, v in cache.stats().items():
        print(f"  {k:<13} = {v}")


if __name__ == "__main__":
    main()
