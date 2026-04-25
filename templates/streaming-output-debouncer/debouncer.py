"""Coalesce streaming tokens within a min interval and a max buffer size.

Why: Naive streaming flushes on every token, which floods downstream UIs and
inflates per-flush overhead (websocket frames, render passes, log lines). A
debouncer batches chunks and flushes on whichever fires first: the time
window expires, or the buffer reaches a size cap.

Stdlib only. Single-threaded; pass `now()` explicitly so callers can use real
time, monotonic time, or a fake clock for tests.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable


@dataclass
class FlushEvent:
    at: float           # timestamp of the flush
    payload: str        # joined chunk text
    chunks: int         # how many raw chunks were coalesced
    reason: str         # "interval" | "buffer" | "final"


@dataclass
class StreamDebouncer:
    min_interval_s: float = 0.050   # 50ms default
    max_buffer_chars: int = 256
    now: Callable[[], float] = time.monotonic
    _buffer: list[str] = field(default_factory=list)
    _buffer_chars: int = 0
    _last_flush: float = field(default=0.0)
    _started: bool = False

    def feed(self, chunk: str) -> FlushEvent | None:
        """Push a chunk. Returns a FlushEvent if a flush was triggered, else None."""
        t = self.now()
        if not self._started:
            self._last_flush = t
            self._started = True
        self._buffer.append(chunk)
        self._buffer_chars += len(chunk)
        # Buffer-size flush takes precedence — protect downstream from huge frames.
        if self._buffer_chars >= self.max_buffer_chars:
            return self._flush(t, reason="buffer")
        # Time-window flush.
        if (t - self._last_flush) >= self.min_interval_s:
            return self._flush(t, reason="interval")
        return None

    def flush_final(self) -> FlushEvent | None:
        """Drain whatever remains. Call once at end of stream."""
        if not self._buffer:
            return None
        return self._flush(self.now(), reason="final")

    def _flush(self, t: float, *, reason: str) -> FlushEvent:
        payload = "".join(self._buffer)
        ev = FlushEvent(at=t, payload=payload, chunks=len(self._buffer), reason=reason)
        self._buffer.clear()
        self._buffer_chars = 0
        self._last_flush = t
        return ev
