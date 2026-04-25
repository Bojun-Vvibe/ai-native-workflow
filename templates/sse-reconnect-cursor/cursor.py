"""
sse-reconnect-cursor — pure cursor-tracker for resumable Server-Sent-Events
style streams (LLM token streams, tool-output streams, log tails).

The transport (urllib / aiohttp / SDK) is the caller's job. This module owns
the *correctness* of resume:

  * track the last delivered event id (`last_event_id`),
  * decide whether a freshly received event should be DELIVERED, SKIPPED
    (already-delivered duplicate after a reconnect), or REJECTED (server
    rewound past our cursor — a real correctness bug, not a hiccup),
  * decide whether we are allowed to reconnect (per-window attempt budget,
    monotonic clock, server-suggested `retry_after_s` honored as a *floor*),
  * never silently lose an id and never silently accept a rewind.

Event id ordering is **monotonic int by contract**, because string ids
(uuids) cannot be safely compared for "did the server rewind?" — and the
silent-rewind bug is exactly what this template exists to prevent.

Stdlib only. No I/O. Inject the clock for deterministic tests.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional


class EventVerdict(str, Enum):
    DELIVER = "deliver"          # new event, advance cursor, hand to consumer
    SKIP_DUPLICATE = "skip"      # event_id <= last_event_id, post-reconnect dup
    REJECT_REWIND = "reject"     # server sent an id strictly between last_id
                                 # and a previously-seen id — protocol violation


class ReconnectVerdict(str, Enum):
    GO = "go"                              # allowed to reconnect now
    WAIT = "wait"                          # honor retry_after / cooldown
    GIVE_UP = "give_up"                    # attempt budget exhausted in window


@dataclass(frozen=True)
class EventDecision:
    verdict: EventVerdict
    new_last_event_id: int               # caller persists this on DELIVER
    reason: str


@dataclass(frozen=True)
class ReconnectDecision:
    verdict: ReconnectVerdict
    wait_s: float                        # 0.0 on GO / GIVE_UP
    attempts_used: int
    attempts_remaining: int
    reason: str


@dataclass
class _Attempt:
    at_s: float


@dataclass
class SseCursor:
    """
    Resumable SSE-style cursor.

    Parameters
    ----------
    max_attempts_per_window:
        Hard cap on reconnect attempts inside `window_s`. The dispatcher
        will give up rather than spin a tight reconnect loop against an
        upstream that is permanently broken.
    window_s:
        Sliding window for the attempt budget. Older attempts age out.
    min_backoff_s:
        Floor between two consecutive reconnects. The server's
        `retry_after_s`, if larger, wins.
    now:
        Monotonic clock callable. Inject for deterministic tests.

    State
    -----
    `last_event_id` is the largest id this cursor has ever DELIVERED.
    A successful run never moves it backwards. A REJECT_REWIND verdict
    leaves it untouched on purpose so the caller can decide to abort
    rather than silently re-process.
    """

    max_attempts_per_window: int
    window_s: float
    min_backoff_s: float
    now: Callable[[], float]
    last_event_id: int = -1
    _attempts: list[_Attempt] = field(default_factory=list)
    # ids we've actually delivered (for rewind detection); kept bounded to
    # a tail so this stays O(1) memory-friendly even on long streams
    _seen_tail: list[int] = field(default_factory=list)
    _seen_tail_cap: int = 1024

    # ---- event-side ------------------------------------------------------

    def consider(self, event_id: int) -> EventDecision:
        if not isinstance(event_id, int) or isinstance(event_id, bool):
            raise TypeError("event_id must be int (use a monotonic counter, not a uuid)")

        if event_id > self.last_event_id:
            # forward progress: deliver and advance
            self.last_event_id = event_id
            self._record_seen(event_id)
            return EventDecision(
                verdict=EventVerdict.DELIVER,
                new_last_event_id=event_id,
                reason="forward_progress",
            )

        # event_id <= last_event_id: either an honest post-reconnect dup,
        # or a rewind. We can only verify dup if we still have it in the
        # tail; if we've evicted it we conservatively treat as duplicate
        # (preferring at-most-once delivery to false-positive rewind alerts).
        if event_id in self._seen_tail or event_id < self._oldest_seen_id():
            return EventDecision(
                verdict=EventVerdict.SKIP_DUPLICATE,
                new_last_event_id=self.last_event_id,
                reason="already_delivered",
            )

        # event_id is in the gap (oldest_seen, last_event_id] but not in
        # our tail — it claims to be a delivered id we never saw. Rewind.
        return EventDecision(
            verdict=EventVerdict.REJECT_REWIND,
            new_last_event_id=self.last_event_id,
            reason=f"server_rewind: id={event_id} <= last={self.last_event_id} but not in delivered tail",
        )

    # ---- reconnect-side --------------------------------------------------

    def consider_reconnect(self, server_retry_after_s: Optional[float] = None) -> ReconnectDecision:
        if server_retry_after_s is not None and server_retry_after_s < 0:
            raise ValueError("server_retry_after_s must be >= 0")

        now = self.now()
        self._evict_old_attempts(now)
        used = len(self._attempts)
        remaining = self.max_attempts_per_window - used

        if remaining <= 0:
            return ReconnectDecision(
                verdict=ReconnectVerdict.GIVE_UP,
                wait_s=0.0,
                attempts_used=used,
                attempts_remaining=0,
                reason=f"attempt_budget_exhausted: {used}/{self.max_attempts_per_window} in {self.window_s:.1f}s",
            )

        # honour both our cooldown floor and the server's hint, whichever
        # is larger (server is allowed to demand more, never less)
        floor = self.min_backoff_s
        if self._attempts:
            since_last = now - self._attempts[-1].at_s
            wait = max(0.0, floor - since_last)
        else:
            wait = 0.0
        if server_retry_after_s is not None:
            wait = max(wait, server_retry_after_s)

        if wait > 0.0:
            return ReconnectDecision(
                verdict=ReconnectVerdict.WAIT,
                wait_s=wait,
                attempts_used=used,
                attempts_remaining=remaining,
                reason="cooldown_or_server_retry_after",
            )

        # going now: claim the slot
        self._attempts.append(_Attempt(at_s=now))
        return ReconnectDecision(
            verdict=ReconnectVerdict.GO,
            wait_s=0.0,
            attempts_used=used + 1,
            attempts_remaining=remaining - 1,
            reason="within_budget",
        )

    # ---- internals -------------------------------------------------------

    def _record_seen(self, event_id: int) -> None:
        self._seen_tail.append(event_id)
        if len(self._seen_tail) > self._seen_tail_cap:
            # drop the oldest half so we don't thrash on every append
            drop = len(self._seen_tail) - self._seen_tail_cap
            del self._seen_tail[:drop]

    def _oldest_seen_id(self) -> int:
        return self._seen_tail[0] if self._seen_tail else -1

    def _evict_old_attempts(self, now: float) -> None:
        cutoff = now - self.window_s
        # attempts are appended in monotonic order; drop from the front
        i = 0
        for a in self._attempts:
            if a.at_s >= cutoff:
                break
            i += 1
        if i:
            del self._attempts[:i]
