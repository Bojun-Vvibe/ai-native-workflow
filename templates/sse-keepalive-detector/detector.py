"""
sse-keepalive-detector — distinguish a healthy-but-idle SSE stream from a stalled one.

The transport layer (urllib / aiohttp / sdk) is the caller's job. This module
owns the *liveness verdict* part most ad-hoc stream watchdogs get wrong:

  - A stream that produces nothing for 30s could be:
      (a) actively streaming tokens slowly,
      (b) idle but the server is sending `: keepalive\\n\\n` comment frames,
      (c) wedged on a TCP connection the kernel hasn't yet noticed is dead.

  Only (c) is a reason to cancel and reconnect. Distinguishing them requires
  separating *real* events from *keepalive* events and applying two separate
  thresholds — which is what this template does.

No I/O, no clocks at construction time — caller injects `now_fn`. Stdlib only.

Public API:
    Detector(real_event_idle_s, keepalive_idle_s, *, now_fn=time.monotonic)
    detector.observe(now, *, kind)        # kind ∈ {"real", "keepalive"}
    detector.snapshot(now=None) -> Snapshot
    detector.verdict(now=None) -> Verdict # "HEALTHY" | "IDLE_BUT_ALIVE" | "STALLED" | "DEAD"

Verdict rules (evaluated against `now`, NOT against last-observe time, so a
watchdog calling verdict() periodically can detect a wedged stream that has
stopped calling observe() entirely):

    DEAD             — never observed any event since construction AND
                       (now - constructed_at) > keepalive_idle_s.
                       i.e. the stream never even sent a keepalive.
    HEALTHY          — saw a real event within real_event_idle_s.
    IDLE_BUT_ALIVE   — no real event within real_event_idle_s, but a keepalive
                       arrived within keepalive_idle_s. Server is alive,
                       just has nothing to say. Do NOT reconnect.
    STALLED          — neither a real event within real_event_idle_s NOR a
                       keepalive within keepalive_idle_s. Connection is
                       almost certainly dead. Caller should cancel + reconnect.

Why two thresholds:
    Real LLM streams send tokens in bursts then pause for tool execution; a
    30s gap between real chunks is normal. Keepalives are supposed to be
    cheap heartbeats — a 30s gap between *those* means the server isn't
    even alive. Conflating the two thresholds either alarms on healthy idle
    streams or misses dead-but-recently-alive ones.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, Literal, Optional

EventKind = Literal["real", "keepalive"]
Verdict = Literal["HEALTHY", "IDLE_BUT_ALIVE", "STALLED", "DEAD"]


class DetectorConfigError(ValueError):
    """Construction-time misconfiguration (better to fail loudly than to silently
    produce a useless detector)."""


@dataclass(frozen=True)
class Snapshot:
    now: float
    constructed_at: float
    last_real_at: Optional[float]
    last_keepalive_at: Optional[float]
    real_event_count: int
    keepalive_count: int
    seconds_since_last_real: Optional[float]
    seconds_since_last_keepalive: Optional[float]
    verdict: Verdict


class Detector:
    def __init__(
        self,
        real_event_idle_s: float,
        keepalive_idle_s: float,
        *,
        now_fn: Callable[[], float] = time.monotonic,
    ) -> None:
        if real_event_idle_s <= 0:
            raise DetectorConfigError(
                f"real_event_idle_s must be > 0, got {real_event_idle_s!r}"
            )
        if keepalive_idle_s <= 0:
            raise DetectorConfigError(
                f"keepalive_idle_s must be > 0, got {keepalive_idle_s!r}"
            )
        # A keepalive idle threshold tighter than the real-event threshold is
        # almost always a config bug — keepalives are supposed to be cheap and
        # frequent, real events expensive and bursty.
        if keepalive_idle_s > real_event_idle_s:
            raise DetectorConfigError(
                f"keepalive_idle_s ({keepalive_idle_s}) must be <= "
                f"real_event_idle_s ({real_event_idle_s}); a server whose "
                f"keepalives are rarer than its real events is misconfigured."
            )
        self._real_event_idle_s = real_event_idle_s
        self._keepalive_idle_s = keepalive_idle_s
        self._now_fn = now_fn
        self._constructed_at = now_fn()
        self._last_real_at: Optional[float] = None
        self._last_keepalive_at: Optional[float] = None
        self._real_event_count = 0
        self._keepalive_count = 0

    def observe(self, now: float, *, kind: EventKind) -> None:
        """Record a single event arriving at wall-time `now`.

        `kind` MUST be "real" or "keepalive". A "real" event is anything the
        caller would surface to its consumer (token chunks, tool-call deltas,
        message events). A "keepalive" is a server-sent frame that exists
        only to keep the connection warm (`:keepalive`, `event: ping`, etc.).

        Real events also count as proof-of-life, so a "real" observation
        implicitly satisfies the keepalive threshold — but a keepalive does
        NOT bump the real-event timestamp (that would defeat the purpose).
        """
        if kind == "real":
            self._last_real_at = now
            # A real event is also proof of life — push the keepalive watermark
            # forward too. Otherwise a chatty stream that never sends explicit
            # keepalives would flap to STALLED the moment real events paused.
            if self._last_keepalive_at is None or now > self._last_keepalive_at:
                self._last_keepalive_at = now
            self._real_event_count += 1
        elif kind == "keepalive":
            self._last_keepalive_at = now
            self._keepalive_count += 1
        else:
            raise ValueError(
                f"kind must be 'real' or 'keepalive', got {kind!r}"
            )

    def verdict(self, now: Optional[float] = None) -> Verdict:
        """Return current liveness verdict. `now` defaults to `now_fn()`."""
        if now is None:
            now = self._now_fn()
        if self._last_real_at is None and self._last_keepalive_at is None:
            # Never observed anything. If we've waited longer than the
            # keepalive window for the very first byte, the stream is dead.
            if (now - self._constructed_at) > self._keepalive_idle_s:
                return "DEAD"
            # Otherwise we're still in the warm-up window.
            return "IDLE_BUT_ALIVE"
        # We've seen at least one event. Apply the two-threshold rule.
        real_ok = (
            self._last_real_at is not None
            and (now - self._last_real_at) <= self._real_event_idle_s
        )
        if real_ok:
            return "HEALTHY"
        keepalive_ok = (
            self._last_keepalive_at is not None
            and (now - self._last_keepalive_at) <= self._keepalive_idle_s
        )
        if keepalive_ok:
            return "IDLE_BUT_ALIVE"
        return "STALLED"

    def snapshot(self, now: Optional[float] = None) -> Snapshot:
        if now is None:
            now = self._now_fn()
        return Snapshot(
            now=now,
            constructed_at=self._constructed_at,
            last_real_at=self._last_real_at,
            last_keepalive_at=self._last_keepalive_at,
            real_event_count=self._real_event_count,
            keepalive_count=self._keepalive_count,
            seconds_since_last_real=(
                None if self._last_real_at is None else now - self._last_real_at
            ),
            seconds_since_last_keepalive=(
                None
                if self._last_keepalive_at is None
                else now - self._last_keepalive_at
            ),
            verdict=self.verdict(now),
        )
