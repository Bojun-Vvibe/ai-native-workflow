"""Retry budget tracker.

Wraps a flaky callable with a *shared* retry budget so a single bad
endpoint cannot consume infinite retries across many concurrent calls.

Two budgets are tracked:

  * per_call_max:   hard cap on retries for ONE logical call
  * window_budget:  shared retry pool refilled at `refill_per_sec`
                    (token-bucket style). When empty, further retries
                    fast-fail with `BudgetExhausted` even if the
                    per-call cap is not yet hit.

This is the "google sre book" retry budget: ratio of retries to
real attempts is bounded so a downstream brownout does not get
amplified by clients pounding it.

Stdlib only. Thread-safe.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Callable, TypeVar

T = TypeVar("T")


class BudgetExhausted(RuntimeError):
    """Raised when the shared retry budget has no tokens left."""


@dataclass
class RetryStats:
    attempts: int = 0          # total first-tries
    retries_used: int = 0      # retries actually consumed from budget
    retries_denied: int = 0    # retries refused because budget empty
    successes: int = 0
    failures: int = 0          # gave up after retries / budget denied


@dataclass
class RetryBudget:
    """Token-bucket retry budget shared across callers."""

    capacity: float
    refill_per_sec: float
    _tokens: float = field(init=False)
    _last_refill: float = field(init=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False)

    def __post_init__(self) -> None:
        self._tokens = float(self.capacity)
        self._last_refill = time.monotonic()

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_refill
        if elapsed > 0:
            self._tokens = min(
                self.capacity, self._tokens + elapsed * self.refill_per_sec
            )
            self._last_refill = now

    def try_consume(self, n: float = 1.0) -> bool:
        with self._lock:
            self._refill()
            if self._tokens >= n:
                self._tokens -= n
                return True
            return False

    def tokens(self) -> float:
        with self._lock:
            self._refill()
            return self._tokens


def call_with_budget(
    fn: Callable[[], T],
    *,
    budget: RetryBudget,
    per_call_max: int,
    stats: RetryStats,
    sleep: Callable[[float], None] = time.sleep,
    backoff_base: float = 0.0,  # 0.0 keeps tests fast; set >0 in real use
) -> T:
    """Call `fn` with retry, bounded by both per-call cap and shared budget.

    Returns the value returned by `fn`. Re-raises the last exception if
    retries are exhausted. Raises BudgetExhausted if the shared budget
    refused a retry.
    """
    stats.attempts += 1
    attempt = 0
    last_exc: BaseException | None = None
    while True:
        try:
            value = fn()
            stats.successes += 1
            return value
        except Exception as exc:
            last_exc = exc
            if attempt >= per_call_max:
                stats.failures += 1
                raise
            if not budget.try_consume(1.0):
                stats.retries_denied += 1
                stats.failures += 1
                raise BudgetExhausted(
                    f"shared retry budget empty after {attempt} retries; "
                    f"last error: {exc!r}"
                ) from exc
            stats.retries_used += 1
            attempt += 1
            if backoff_base > 0:
                sleep(backoff_base * (2 ** (attempt - 1)))
    # unreachable
    assert last_exc is not None
    raise last_exc
