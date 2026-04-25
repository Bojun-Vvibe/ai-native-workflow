"""Tool-call idempotency key.

Wraps any tool callable so that retries within a configurable dedup window
return the cached result instead of re-invoking the underlying tool. The
client generates an idempotency key per *logical* operation; if the same
key arrives again within the TTL, the original result is replayed even if
the underlying side-effecting tool is non-idempotent (e.g. "create issue",
"send notification", "charge credit card").

If the key is reused but the args differ, that is a programming error and
the wrapper raises IdempotencyKeyConflict so the bug surfaces loudly
instead of returning a wrong cached result.

If a prior call is still in-flight when a duplicate key arrives, the
duplicate raises IdempotencyKeyInFlight (the caller is responsible for
deciding whether to wait, retry later, or fail). This is intentional:
silent blocking inside a synchronous wrapper hides bugs.

Args canonicalization: a stable JSON dump (sort_keys=True, separators
trimmed). The key + sha256 of that canonical form forms the cache index;
a mismatch on the same key is the conflict signal.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional, Tuple


class IdempotencyKeyConflict(Exception):
    """Same key, different arguments -> almost always a client bug."""


class IdempotencyKeyInFlight(Exception):
    """Same key while the original call has not yet returned."""


def _canonical_args_hash(args: tuple, kwargs: dict) -> str:
    payload = {"args": list(args), "kwargs": kwargs}
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


@dataclass
class _Entry:
    args_hash: str
    started_at: float
    completed_at: Optional[float]
    result: Any
    error: Optional[BaseException]

    @property
    def in_flight(self) -> bool:
        return self.completed_at is None


class IdempotencyCache:
    """Bounded TTL cache of (key -> Entry). Single-process, thread-naive
    by design — wire your own lock if you need cross-thread safety.
    """

    def __init__(
        self,
        ttl_seconds: float = 300.0,
        max_entries: int = 1024,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        if max_entries <= 0:
            raise ValueError("max_entries must be positive")
        self._ttl = ttl_seconds
        self._max = max_entries
        self._now = clock
        self._entries: Dict[str, _Entry] = {}

    def _gc(self) -> None:
        now = self._now()
        dead = [k for k, e in self._entries.items()
                if e.completed_at is not None and (now - e.completed_at) > self._ttl]
        for k in dead:
            del self._entries[k]
        # If still oversize, drop oldest completed entries.
        if len(self._entries) > self._max:
            completed = sorted(
                ((k, e) for k, e in self._entries.items() if e.completed_at is not None),
                key=lambda kv: kv[1].completed_at,
            )
            for k, _ in completed[: len(self._entries) - self._max]:
                del self._entries[k]

    def get(self, key: str, args_hash: str) -> Tuple[str, Any]:
        """Return (status, payload). status in {"miss", "hit", "in_flight"}.

        Raises IdempotencyKeyConflict if key matches but args_hash doesn't.
        On "hit" payload is (result, error_or_None); caller must re-raise error if set.
        """
        self._gc()
        e = self._entries.get(key)
        if e is None:
            return ("miss", None)
        if e.args_hash != args_hash:
            raise IdempotencyKeyConflict(
                f"idempotency key {key!r} reused with different arguments"
            )
        if e.in_flight:
            return ("in_flight", None)
        return ("hit", (e.result, e.error))

    def reserve(self, key: str, args_hash: str) -> None:
        self._entries[key] = _Entry(
            args_hash=args_hash,
            started_at=self._now(),
            completed_at=None,
            result=None,
            error=None,
        )

    def complete(self, key: str, result: Any, error: Optional[BaseException]) -> None:
        e = self._entries.get(key)
        if e is None:
            return
        e.result = result
        e.error = error
        e.completed_at = self._now()


def with_idempotency(
    cache: IdempotencyCache,
    func: Callable[..., Any],
) -> Callable[..., Any]:
    """Wrap func so the first positional kwarg `idempotency_key` triggers caching."""

    def wrapped(*args: Any, idempotency_key: str, **kwargs: Any) -> Any:
        if not isinstance(idempotency_key, str) or not idempotency_key:
            raise ValueError("idempotency_key must be a non-empty string")
        ah = _canonical_args_hash(args, kwargs)
        status, payload = cache.get(idempotency_key, ah)
        if status == "hit":
            result, err = payload  # type: ignore[misc]
            if err is not None:
                raise err
            return result
        if status == "in_flight":
            raise IdempotencyKeyInFlight(
                f"idempotency key {idempotency_key!r} is still in flight"
            )
        cache.reserve(idempotency_key, ah)
        try:
            result = func(*args, **kwargs)
        except BaseException as e:
            cache.complete(idempotency_key, None, e)
            raise
        cache.complete(idempotency_key, result, None)
        return result

    return wrapped
