"""Embedding cache with hybrid LRU + TTL + size-bounded eviction.

Why this exists
---------------
Embedding calls are cheap per-unit but add up fast in agent loops that
re-embed near-duplicate text (chunked docs, retried tool outputs, repeated
user messages). A naive dict cache leaks memory; pure LRU keeps stale
vectors forever; pure TTL evicts hot keys. This template combines all three
with a deterministic, observable eviction policy.

Contract
--------
- ``get(key)`` returns the cached vector or ``None``. A hit refreshes
  recency. An expired entry is treated as a miss and removed.
- ``put(key, vector)`` stores the vector and timestamp. If the cache is
  over ``max_entries`` after insert, the *least-recently-used* entry is
  evicted (after first dropping any TTL-expired entries).
- ``stats()`` returns counters (hits, misses, expirations, evictions) so
  you can chart hit-ratio over time.
- Eviction order is fully deterministic for a given access sequence,
  which makes it testable.

Edge cases
----------
- Inserting an existing key updates the vector and refreshes recency
  (counts as a write, not a hit).
- ``ttl_seconds=None`` disables time-based expiration (pure LRU).
- ``max_entries=0`` is rejected; you almost certainly mean "disable
  caching" which you should express by not constructing the cache.
"""

from __future__ import annotations

import time
from collections import OrderedDict
from typing import Callable, Optional, Sequence


class EmbeddingCache:
    def __init__(
        self,
        max_entries: int,
        ttl_seconds: Optional[float] = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if max_entries <= 0:
            raise ValueError("max_entries must be > 0; don't construct the cache if you want it disabled")
        if ttl_seconds is not None and ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be > 0 or None")
        self._max = max_entries
        self._ttl = ttl_seconds
        self._clock = clock
        self._data: "OrderedDict[str, tuple[Sequence[float], float]]" = OrderedDict()
        self._hits = 0
        self._misses = 0
        self._expirations = 0
        self._evictions = 0

    def _expired(self, ts: float, now: float) -> bool:
        return self._ttl is not None and (now - ts) > self._ttl

    def _sweep_expired(self, now: float) -> None:
        if self._ttl is None:
            return
        # Walk from oldest insertion order; OrderedDict preserves insertion,
        # but recency-on-access makes "oldest" not always "first". We must
        # check every entry. Worst case O(n) per sweep, amortized cheap
        # because we only sweep on miss/insert, not on hit.
        dead = [k for k, (_, ts) in self._data.items() if self._expired(ts, now)]
        for k in dead:
            del self._data[k]
            self._expirations += 1

    def get(self, key: str) -> Optional[Sequence[float]]:
        now = self._clock()
        entry = self._data.get(key)
        if entry is None:
            self._misses += 1
            return None
        vector, ts = entry
        if self._expired(ts, now):
            del self._data[key]
            self._expirations += 1
            self._misses += 1
            return None
        # Refresh recency.
        self._data.move_to_end(key)
        self._hits += 1
        return vector

    def put(self, key: str, vector: Sequence[float]) -> None:
        now = self._clock()
        if key in self._data:
            self._data[key] = (vector, now)
            self._data.move_to_end(key)
            return
        self._sweep_expired(now)
        self._data[key] = (vector, now)
        # Evict LRU until under cap.
        while len(self._data) > self._max:
            self._data.popitem(last=False)
            self._evictions += 1

    def __len__(self) -> int:
        return len(self._data)

    def stats(self) -> dict:
        total = self._hits + self._misses
        return {
            "size": len(self._data),
            "max_entries": self._max,
            "hits": self._hits,
            "misses": self._misses,
            "expirations": self._expirations,
            "evictions": self._evictions,
            "hit_ratio": (self._hits / total) if total else 0.0,
        }
