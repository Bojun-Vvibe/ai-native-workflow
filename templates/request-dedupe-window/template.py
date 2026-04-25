"""Sliding-window request deduplicator.

A small, pure helper that suppresses identical requests issued within a
sliding time window. Useful in front of expensive or non-idempotent calls
where the same logical request can be re-issued in quick succession by:

  - retry loops that fired before the first response landed,
  - users mashing buttons,
  - agents looping on partial traces and re-emitting the same call.

This is the *time-windowed* sibling of `tool-call-deduplication` (which uses
a fixed cache size and absolute eviction). Here every entry has its own
"first seen at t" timestamp; a duplicate is only suppressed if seen within
``window_seconds`` of the *first* observation. After the window elapses, the
same key is allowed through again (the duplicate gate is *temporal*, not
permanent).

Design rules:

- Caller supplies ``key_fn(request) -> str`` (canonicalization is the
  caller's responsibility — keep this template policy-free).
- ``now_fn`` is injected for deterministic tests.
- ``submit(request)`` returns ``DedupeDecision(verdict, key, first_seen_at,
  age_s, suppressed_count)`` where verdict is ``"forward"`` or ``"suppress"``.
- ``forward`` means "this is the first or first-after-window observation —
  the caller should actually do the work".
- ``suppress`` means "an identical request is in-flight or was issued
  ``age_s`` seconds ago, within the window — drop or short-circuit".
- Lazy expiry on submit + an explicit ``sweep()`` for callers that want a
  background broom. Memory stays bounded by the active key count within
  the window, not the lifetime call count.
- ``stats()`` returns a deterministic snapshot for logging / metrics.

Stdlib-only.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional


@dataclass(frozen=True)
class DedupeDecision:
    verdict: str               # "forward" | "suppress"
    key: str
    first_seen_at: float       # wall-clock (per now_fn) of the original
    age_s: float               # 0.0 for forward; seconds since first_seen_at otherwise
    suppressed_count: int      # how many times this key has been suppressed so far


@dataclass
class _Entry:
    first_seen_at: float
    suppressed_count: int = 0


class RequestDedupeWindow:
    def __init__(
        self,
        window_seconds: float,
        key_fn: Callable[[Any], str],
        now_fn: Optional[Callable[[], float]] = None,
    ) -> None:
        if window_seconds <= 0:
            raise ValueError("window_seconds must be > 0")
        if not callable(key_fn):
            raise TypeError("key_fn must be callable")
        self._window = float(window_seconds)
        self._key_fn = key_fn
        self._now = now_fn if now_fn is not None else time.monotonic
        self._entries: Dict[str, _Entry] = {}

    @property
    def window_seconds(self) -> float:
        return self._window

    def submit(self, request: Any) -> DedupeDecision:
        """Decide whether to forward `request` or suppress as a duplicate."""
        key = self._key_fn(request)
        if not isinstance(key, str) or not key:
            raise ValueError("key_fn must return a non-empty str")
        now = self._now()
        entry = self._entries.get(key)
        if entry is None or (now - entry.first_seen_at) >= self._window:
            # First observation, or window has elapsed: forward and reset.
            self._entries[key] = _Entry(first_seen_at=now, suppressed_count=0)
            return DedupeDecision(
                verdict="forward",
                key=key,
                first_seen_at=now,
                age_s=0.0,
                suppressed_count=0,
            )
        # Within window of the original: suppress.
        entry.suppressed_count += 1
        return DedupeDecision(
            verdict="suppress",
            key=key,
            first_seen_at=entry.first_seen_at,
            age_s=now - entry.first_seen_at,
            suppressed_count=entry.suppressed_count,
        )

    def sweep(self) -> int:
        """Remove all entries whose window has elapsed. Returns evicted count."""
        now = self._now()
        stale = [k for k, e in self._entries.items() if (now - e.first_seen_at) >= self._window]
        for k in stale:
            del self._entries[k]
        return len(stale)

    def active_keys(self) -> int:
        """Number of entries currently within their window (lazy: doesn't sweep)."""
        return len(self._entries)

    def stats(self) -> Dict[str, Any]:
        now = self._now()
        live = 0
        total_suppressed = 0
        for e in self._entries.values():
            if (now - e.first_seen_at) < self._window:
                live += 1
            total_suppressed += e.suppressed_count
        # Sorted-key snapshot for deterministic logging.
        return {
            "active_keys_live": live,
            "active_keys_total": len(self._entries),
            "total_suppressed": total_suppressed,
            "window_seconds": self._window,
        }
