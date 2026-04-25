"""sse-event-replayer — durable replay of a recorded SSE-style event log.

The companion of `sse-reconnect-cursor`. The cursor template owns the
*consumer*-side correctness of resume (don't re-deliver, don't silently
rewind, don't tight-loop on a dead upstream). This template owns the
*producer*-side correctness: given a `Last-Event-ID` cursor handed back
by a reconnecting client, return the *correct* tail of the recorded
stream — without re-delivering already-acknowledged events, without
returning stale duplicates of an event whose payload changed mid-stream,
and with a clear "you are too far behind, the log already rolled" answer
when the requested cursor has fallen out of the retention window.

Pure stdlib. No I/O on the hot path; the log is held in memory after
construction (durable persistence is the caller's concern; see
`durability` note below). Event ids are monotonically-increasing `int`
(the same constraint `sse-reconnect-cursor` insists on — UUIDs cannot
be safely compared for "is X strictly older than Y").
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable


class EventLogError(Exception):
    """Base for replayer-side log errors."""


class NonMonotonicId(EventLogError):
    """append() saw an id <= the last appended id."""


class IdPayloadConflict(EventLogError):
    """append() saw a duplicate id with a *different* payload.

    Same-id-same-payload is silently absorbed (idempotent re-append from
    a flaky writer is a normal occurrence); same-id-different-payload is
    a producer bug we refuse to silently paper over.
    """


@dataclass(frozen=True)
class Event:
    """One recorded event. ``payload`` is opaque bytes-or-str-or-dict —
    the replayer never inspects it, only compares for equality on
    duplicate-append."""

    id: int
    event: str
    payload: Any


@dataclass(frozen=True)
class ReplayResult:
    """Verdict + payload for a `since(last_event_id)` request."""

    verdict: str  # "DELIVER" | "EMPTY" | "TOO_OLD" | "FUTURE_CURSOR"
    events: tuple[Event, ...] = ()
    # On TOO_OLD: smallest id we still hold, so the caller can ask
    # the consumer to either restart from scratch or fall back to a
    # snapshot.
    oldest_retained_id: int | None = None
    # On FUTURE_CURSOR: latest id we have, so the caller can decide
    # whether to wait or treat the consumer's cursor as corrupt.
    latest_id: int | None = None


@dataclass
class ReplayerStats:
    appended: int = 0
    duplicate_absorbed: int = 0
    deliver_calls: int = 0
    empty_calls: int = 0
    too_old_calls: int = 0
    future_cursor_calls: int = 0
    evicted: int = 0


@dataclass
class EventReplayer:
    """In-memory bounded-retention SSE event replayer.

    Retention policy is *count-based* (``max_retained``). A time-based
    policy is a trivial extension (inject a clock; evict where
    ``now - event_wallclock > ttl``) but adds an injected-clock surface
    we did not need for the worked example.

    Durability: this class is **not** itself durable. A real deployment
    pairs it with an append-only on-disk log (one JSONL row per event)
    that the producer writes to *before* calling ``append`` here, and
    that gets replayed into a fresh ``EventReplayer`` on process
    restart. Keeping durability out of this class lets the test suite
    drive it deterministically without touching the filesystem.
    """

    max_retained: int = 1024
    _events: list[Event] = field(default_factory=list)
    stats: ReplayerStats = field(default_factory=ReplayerStats)

    # ------------------------------------------------------------------
    # producer-facing surface
    # ------------------------------------------------------------------
    def append(self, event: Event) -> None:
        if not isinstance(event.id, int) or isinstance(event.id, bool):
            raise TypeError("event.id must be a plain int")
        if self._events:
            last_id = self._events[-1].id
            if event.id == last_id:
                # Idempotent re-append: same payload is fine, different
                # payload is a producer bug.
                if self._events[-1].payload != event.payload or self._events[-1].event != event.event:
                    raise IdPayloadConflict(
                        f"id={event.id} re-appended with different payload"
                    )
                self.stats.duplicate_absorbed += 1
                return
            if event.id < last_id:
                raise NonMonotonicId(
                    f"id={event.id} <= last_id={last_id}; producer is not monotonic"
                )
        self._events.append(event)
        self.stats.appended += 1
        # Bounded retention.
        while len(self._events) > self.max_retained:
            self._events.pop(0)
            self.stats.evicted += 1

    def extend(self, events: Iterable[Event]) -> None:
        for e in events:
            self.append(e)

    # ------------------------------------------------------------------
    # consumer-facing surface
    # ------------------------------------------------------------------
    def since(self, last_event_id: int | None) -> ReplayResult:
        """Return events strictly after ``last_event_id``.

        ``last_event_id is None`` means "this consumer has never
        connected before" — deliver everything we still hold.

        Verdicts:
          * DELIVER         — we have one or more events to ship.
          * EMPTY           — cursor is current, nothing to ship.
          * TOO_OLD         — cursor predates ``oldest_retained_id``;
                              consumer must restart from snapshot.
          * FUTURE_CURSOR   — cursor is *ahead* of our latest id; the
                              consumer is talking to a stale replica
                              or its state is corrupt.
        """
        if last_event_id is not None:
            if not isinstance(last_event_id, int) or isinstance(last_event_id, bool):
                raise TypeError("last_event_id must be int or None")

        if not self._events:
            if last_event_id is None:
                self.stats.empty_calls += 1
                return ReplayResult(verdict="EMPTY")
            # Empty log + non-None cursor: we cannot prove anything
            # about the cursor's validity. Treat as EMPTY so the
            # consumer simply waits for new traffic.
            self.stats.empty_calls += 1
            return ReplayResult(verdict="EMPTY")

        oldest = self._events[0].id
        latest = self._events[-1].id

        if last_event_id is None:
            self.stats.deliver_calls += 1
            return ReplayResult(verdict="DELIVER", events=tuple(self._events))

        if last_event_id > latest:
            self.stats.future_cursor_calls += 1
            return ReplayResult(verdict="FUTURE_CURSOR", latest_id=latest)

        if last_event_id == latest:
            self.stats.empty_calls += 1
            return ReplayResult(verdict="EMPTY")

        # last_event_id < latest. Either it's >= oldest-1 (we can serve
        # the tail) or it's strictly less than oldest-1 (we evicted it).
        if last_event_id < oldest - 1:
            # Note: == oldest-1 means "deliver from oldest onwards" and
            # is fine. < oldest-1 means we already evicted at least one
            # event the consumer has not seen.
            self.stats.too_old_calls += 1
            return ReplayResult(verdict="TOO_OLD", oldest_retained_id=oldest)

        # Binary-search would be nicer at very large retention; linear
        # is plenty for any sane SSE event log.
        tail = tuple(e for e in self._events if e.id > last_event_id)
        self.stats.deliver_calls += 1
        return ReplayResult(verdict="DELIVER", events=tail)

    # ------------------------------------------------------------------
    # introspection
    # ------------------------------------------------------------------
    def snapshot(self) -> dict[str, Any]:
        return {
            "retained": len(self._events),
            "max_retained": self.max_retained,
            "oldest_id": self._events[0].id if self._events else None,
            "latest_id": self._events[-1].id if self._events else None,
            "stats": {
                "appended": self.stats.appended,
                "duplicate_absorbed": self.stats.duplicate_absorbed,
                "deliver_calls": self.stats.deliver_calls,
                "empty_calls": self.stats.empty_calls,
                "too_old_calls": self.stats.too_old_calls,
                "future_cursor_calls": self.stats.future_cursor_calls,
                "evicted": self.stats.evicted,
            },
        }
