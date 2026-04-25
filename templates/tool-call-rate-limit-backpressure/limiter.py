"""Bounded-queue rate limiter with explicit backpressure for tool calls.

Problem: agents can submit tool calls faster than the downstream tool
can serve them. Three failure modes if you don't push back:

  1. Unbounded in-process queue → OOM under sustained over-submission.
  2. Token-bucket-only rate limit → caller submits 10k requests, all
     queued, none rejected; latency explodes silently and the agent
     keeps acting on a stale belief that everything is "in flight ok".
  3. Drop-newest with no signal → caller cannot distinguish
     "submitted, will be served eventually" from "silently dropped",
     so retries layer on retries and amplify the brownout.

This template is the runtime-control answer: a bounded FIFO + a token
bucket gate, where `submit()` returns one of THREE explicit verdicts —
`Admitted` (work is enqueued, here is your ticket), `Throttled` (queue
has room but the bucket is empty; the caller should backoff for
`retry_after_s`), or `Rejected` (queue is full and the caller should
shed load entirely). The caller is forced to make a load-shedding
decision at submit time instead of after the fact.

Design choices:

* Token bucket is monotonic-clock based and refills lazily on
  `submit()` and `complete()`. No background thread, no `time.sleep`.
* Queue is bounded; `Rejected` returns `queue_depth` so callers can
  reason about how loaded the upstream is.
* `complete(ticket_id)` is explicit so the limiter knows when a slot
  frees; this is more honest than time-based "in-flight estimation".
* `now_fn` is injected so tests are deterministic.
* Single-threaded in-process. No `Lock`. Wrap externally if you need
  multi-threading — the algorithm doesn't change.

Composes with:
  - tool-call-circuit-breaker: breaker says "this tool is unhealthy";
    this limiter says "even healthy, you're submitting too fast".
  - retry-budget-tracker: shared retry budget across callers; this
    limiter is per-tool admission.
  - structured-error-taxonomy: Throttled → retryable_after_backoff;
    Rejected → caller_shed_load.
"""

from __future__ import annotations

import itertools
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Callable, Deque, Optional


# ---------- verdicts ----------


@dataclass(frozen=True)
class Admitted:
    ticket_id: int
    enqueued_at: float
    queue_depth_after: int  # depth INCLUDING this call


@dataclass(frozen=True)
class Throttled:
    retry_after_s: float
    queue_depth: int  # current depth, this call NOT enqueued


@dataclass(frozen=True)
class Rejected:
    queue_depth: int  # at-capacity depth, this call NOT enqueued
    queue_capacity: int


Verdict = Admitted | Throttled | Rejected


# ---------- limiter ----------


@dataclass
class RateLimitBackpressure:
    rate_per_sec: float                # bucket refill rate
    burst: int                         # bucket capacity
    queue_capacity: int                # bounded FIFO size
    now_fn: Callable[[], float] = time.monotonic
    _tokens: float = field(init=False)
    _last_refill: float = field(init=False)
    _queue: Deque[int] = field(default_factory=deque, init=False)
    _ids: itertools.count = field(default_factory=lambda: itertools.count(1), init=False)
    # observability counters
    admitted_count: int = 0
    throttled_count: int = 0
    rejected_count: int = 0
    completed_count: int = 0

    def __post_init__(self) -> None:
        if self.rate_per_sec <= 0:
            raise ValueError("rate_per_sec must be > 0")
        if self.burst < 1:
            raise ValueError("burst must be >= 1")
        if self.queue_capacity < 1:
            raise ValueError("queue_capacity must be >= 1")
        self._tokens = float(self.burst)
        self._last_refill = self.now_fn()

    # ---------- public API ----------

    def submit(self) -> Verdict:
        self._refill()
        depth = len(self._queue)
        if depth >= self.queue_capacity:
            self.rejected_count += 1
            return Rejected(queue_depth=depth, queue_capacity=self.queue_capacity)
        if self._tokens < 1.0:
            # Queue has room, but no token. Tell caller exactly how
            # long until one token has refilled.
            deficit = 1.0 - self._tokens
            retry_after = deficit / self.rate_per_sec
            self.throttled_count += 1
            return Throttled(retry_after_s=retry_after, queue_depth=depth)
        # Admit: spend one token, take a ticket.
        self._tokens -= 1.0
        ticket_id = next(self._ids)
        self._queue.append(ticket_id)
        self.admitted_count += 1
        return Admitted(
            ticket_id=ticket_id,
            enqueued_at=self.now_fn(),
            queue_depth_after=len(self._queue),
        )

    def complete(self, ticket_id: int) -> None:
        """Caller signals that a previously-admitted call has finished
        (success OR failure — both free the queue slot)."""
        try:
            self._queue.remove(ticket_id)
        except ValueError:
            raise UnknownTicket(f"unknown or already-completed ticket: {ticket_id}")
        self.completed_count += 1

    @property
    def queue_depth(self) -> int:
        return len(self._queue)

    @property
    def tokens_available(self) -> float:
        self._refill()
        return self._tokens

    # ---------- internals ----------

    def _refill(self) -> None:
        now = self.now_fn()
        elapsed = now - self._last_refill
        if elapsed <= 0:
            return
        self._tokens = min(float(self.burst), self._tokens + elapsed * self.rate_per_sec)
        self._last_refill = now


class UnknownTicket(Exception):
    pass
