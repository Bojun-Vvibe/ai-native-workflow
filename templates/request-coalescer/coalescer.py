"""In-flight request coalescer.

Collapses N concurrent identical requests into 1 upstream call. The
first caller for a given key triggers the upstream call; every
subsequent caller arriving while that call is still in flight is
attached to the same future and receives the same result (or the same
exception). Once the call completes, the in-flight slot is released
immediately — this is *not* a result cache; the very next call after
completion fires upstream again.

This is the right tool when:

  - The upstream call is expensive (LLM completion, vector search,
    cold S3 read) but its result is not necessarily cacheable across
    time (the truly-cacheable case wants `templates/tool-result-cache`).
  - Your service has bursty fan-in: a webhook arrives, ten parallel
    handlers all hit the same `expand_user(user_id=42)` lookup.
  - You cannot or do not want to add a result cache (auth-sensitive,
    rapidly-changing, large blobs you don't want resident).

It is the wrong tool when:

  - You want results to survive across the moment of fan-in. Use
    `tool-result-cache` and configure a `ttl_s`.
  - The upstream call has side effects. Coalescing two `POST /charge`
    calls into one would silently swallow the second charge. The
    coalescer raises `CoalescerError` if the caller has not declared
    the operation idempotent.

Stdlib-only. The reference implementation is sync-thread-safe via a
single `threading.Lock`; the SPEC describes the equivalent asyncio
shape (one `asyncio.Future` per key, no lock needed when the loop is
single-threaded).
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Tuple


class CoalescerError(Exception):
    """Raised on misuse (non-idempotent op, missing key fn, etc.)."""


@dataclass
class _Slot:
    event: threading.Event = field(default_factory=threading.Event)
    result: Any = None
    error: BaseException | None = None
    waiters: int = 0  # leader counts as 1


@dataclass
class CoalescerStats:
    leaders: int = 0  # upstream calls actually issued
    followers: int = 0  # callers attached to an in-flight slot
    errors: int = 0  # leader calls that raised


class RequestCoalescer:
    """Per-key in-flight coalescer.

    Construct with:
      - key_fn(*args, **kwargs) -> hashable key
      - safe_for_coalescing: bool — explicit caller declaration that
        the wrapped op is side-effect-free. Defaults to False; calling
        without setting True raises CoalescerError on the first call.
    """

    def __init__(
        self,
        key_fn: Callable[..., Tuple[Any, ...]],
        *,
        safe_for_coalescing: bool = False,
    ) -> None:
        if key_fn is None:
            raise CoalescerError("key_fn is required")
        self._key_fn = key_fn
        self._safe = safe_for_coalescing
        self._lock = threading.Lock()
        self._inflight: Dict[Any, _Slot] = {}
        self.stats = CoalescerStats()

    def call(self, fn: Callable[..., Any], *args, **kwargs) -> Any:
        if not self._safe:
            raise CoalescerError(
                "RequestCoalescer requires explicit safe_for_coalescing=True; "
                "coalescing operations with side effects silently swallows them."
            )
        key = self._key_fn(*args, **kwargs)
        with self._lock:
            slot = self._inflight.get(key)
            if slot is None:
                slot = _Slot(waiters=1)
                self._inflight[key] = slot
                is_leader = True
                self.stats.leaders += 1
            else:
                slot.waiters += 1
                is_leader = False
                self.stats.followers += 1
        if is_leader:
            try:
                slot.result = fn(*args, **kwargs)
            except BaseException as exc:
                slot.error = exc
                self.stats.errors += 1
            finally:
                slot.event.set()
                with self._lock:
                    # Release the slot the instant the call completes,
                    # whether it succeeded or failed. This is what makes
                    # the coalescer NOT a cache.
                    self._inflight.pop(key, None)
        else:
            slot.event.wait()
        if slot.error is not None:
            raise slot.error
        return slot.result

    def state(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "inflight_keys": sorted(map(str, self._inflight.keys())),
                "leaders": self.stats.leaders,
                "followers": self.stats.followers,
                "errors": self.stats.errors,
            }
