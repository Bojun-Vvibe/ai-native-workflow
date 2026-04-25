"""
streaming-token-rate-meter — pure rate / latency observer for streamed
LLM token output (or any chunked stream).

Calling code feeds it `observe(now_s, tokens_delta)` once per arriving
chunk. The meter maintains:

  * time-to-first-token (TTFT)
  * tokens/sec over a sliding wall-clock window (default 1.0s)
  * inter-chunk gap statistics (last gap, max gap)
  * a stall verdict: tokens have stopped arriving for > stall_threshold_s
  * cumulative totals

The meter does NOT cancel the stream, sleep, or call the network. It
returns a snapshot the caller can decide on (cancel? warn? log?).

Why a sliding window and not a single EWMA: agents care about "did the
upstream just slow to a crawl in the last second" much more than the
long-run mean. EWMAs are over-smoothed for this question. The window is
a deque of (t, n) samples; old samples age out lazily on the next call.

Stdlib only. Inject the clock for tests.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Callable, Deque, Optional


@dataclass(frozen=True)
class RateSnapshot:
    elapsed_s: float
    total_tokens: int
    chunks_seen: int
    ttft_s: Optional[float]            # None until first non-zero chunk
    window_tokens_per_s: float         # over the last `window_s` of wall clock
    last_gap_s: Optional[float]        # gap between last two chunks
    max_gap_s: float                   # largest inter-chunk gap so far
    is_stalled: bool                   # last_gap_s > stall_threshold_s
    cumulative_tokens_per_s: float     # total / elapsed (stable for whole-run reports)


@dataclass
class _Sample:
    t: float
    n: int


@dataclass
class StreamingTokenRateMeter:
    """
    Parameters
    ----------
    window_s:
        Sliding window for the recent tokens/sec figure.
    stall_threshold_s:
        If the most recent inter-chunk gap exceeds this, `is_stalled=True`
        on the *next* snapshot. The meter never stalls itself — the
        caller decides what to do.
    now:
        Monotonic clock for `start()` and for `snapshot()` calls that
        don't supply a `now_s`. Inject for deterministic tests.
    """

    window_s: float = 1.0
    stall_threshold_s: float = 2.0
    now: Callable[[], float] = None  # type: ignore[assignment]

    _started_at: Optional[float] = None
    _last_chunk_at: Optional[float] = None
    _ttft_s: Optional[float] = None
    _samples: Deque[_Sample] = field(default_factory=deque)
    _total: int = 0
    _chunks: int = 0
    _max_gap_s: float = 0.0
    _last_gap_s: Optional[float] = None

    def __post_init__(self) -> None:
        if self.window_s <= 0:
            raise ValueError("window_s must be > 0")
        if self.stall_threshold_s <= 0:
            raise ValueError("stall_threshold_s must be > 0")
        if self.now is None:
            import time
            self.now = time.monotonic

    def start(self, at_s: Optional[float] = None) -> None:
        """Mark the moment the request was sent (for TTFT)."""
        if self._started_at is not None:
            raise RuntimeError("start() called twice on the same meter")
        self._started_at = at_s if at_s is not None else self.now()

    def observe(self, now_s: float, tokens_delta: int) -> None:
        if self._started_at is None:
            raise RuntimeError("observe() called before start()")
        if tokens_delta < 0:
            raise ValueError("tokens_delta must be >= 0")
        if now_s < self._started_at:
            raise ValueError(f"now_s={now_s} precedes start={self._started_at}")
        if self._last_chunk_at is not None and now_s < self._last_chunk_at:
            raise ValueError("clock went backwards between observe() calls")

        # heartbeat / keepalive chunks (0 tokens) still update gap state but
        # never set TTFT and never count toward the throughput window
        if tokens_delta > 0:
            if self._ttft_s is None:
                self._ttft_s = now_s - self._started_at
            self._samples.append(_Sample(t=now_s, n=tokens_delta))
            self._total += tokens_delta

        if self._last_chunk_at is not None:
            gap = now_s - self._last_chunk_at
            self._last_gap_s = gap
            if gap > self._max_gap_s:
                self._max_gap_s = gap
        self._last_chunk_at = now_s
        self._chunks += 1

    def snapshot(self, now_s: Optional[float] = None) -> RateSnapshot:
        if self._started_at is None:
            raise RuntimeError("snapshot() called before start()")
        t = now_s if now_s is not None else self.now()
        if t < self._started_at:
            raise ValueError("snapshot now_s precedes start")

        # evict samples older than the window relative to `t`
        cutoff = t - self.window_s
        while self._samples and self._samples[0].t < cutoff:
            self._samples.popleft()

        elapsed = t - self._started_at
        window_tokens = sum(s.n for s in self._samples)
        # divide by the actual window length (not by elapsed) so a fast
        # last second isn't diluted by a slow first 30s
        wps = window_tokens / self.window_s

        # if the meter has been silent for longer than the window, the
        # window is empty and `wps == 0.0` — that's correct, and it
        # combines with `is_stalled` for the caller's decision.

        # is_stalled uses *current time*, not last_chunk_at, so the meter
        # stalls even if no new chunk arrived
        if self._last_chunk_at is not None:
            current_gap = t - self._last_chunk_at
            stalled = current_gap > self.stall_threshold_s
            # don't update _max_gap_s here — _max_gap_s tracks gaps
            # between observed chunks, not "open" gaps. The current_gap
            # is exposed via is_stalled / last_gap_s separately.
        else:
            stalled = elapsed > self.stall_threshold_s

        cum_wps = (self._total / elapsed) if elapsed > 0 else 0.0

        return RateSnapshot(
            elapsed_s=round(elapsed, 6),
            total_tokens=self._total,
            chunks_seen=self._chunks,
            ttft_s=round(self._ttft_s, 6) if self._ttft_s is not None else None,
            window_tokens_per_s=round(wps, 6),
            last_gap_s=round(self._last_gap_s, 6) if self._last_gap_s is not None else None,
            max_gap_s=round(self._max_gap_s, 6),
            is_stalled=stalled,
            cumulative_tokens_per_s=round(cum_wps, 6),
        )
