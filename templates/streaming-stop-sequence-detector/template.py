"""Streaming stop-sequence detector.

Incrementally scans a stream of token/text chunks for any of N stop sequences.
The hard part: a stop sequence may straddle chunk boundaries (e.g. chunk A
ends with "</" and chunk B starts with "stop>"). This detector buffers the
minimum tail required (max_stop_len - 1) so it never misses a boundary match,
while still emitting "safe" prefix bytes downstream as early as possible.

Usage:
    det = StopSequenceDetector(["</stop>", "\n\nUser:"])
    for chunk in stream:
        emit, hit = det.feed(chunk)
        sink.write(emit)
        if hit is not None:
            # hit = (stop_string, position_in_emit_or_buffer)
            break
    # Always flush remaining buffer when stream ends without a hit:
    sink.write(det.flush())
"""

from __future__ import annotations

from typing import List, Optional, Tuple


class StopSequenceDetector:
    def __init__(self, stops: List[str]) -> None:
        if not stops:
            raise ValueError("at least one stop sequence required")
        if any(not s for s in stops):
            raise ValueError("empty stop sequence not allowed")
        self._stops = list(stops)
        self._max_len = max(len(s) for s in self._stops)
        self._buf = ""
        self._done = False

    def feed(self, chunk: str) -> Tuple[str, Optional[Tuple[str, int]]]:
        """Feed one chunk. Returns (safe_to_emit, hit).

        hit is None if no stop matched yet, otherwise (stop_string, index_in_combined)
        where combined = previous_buffer + chunk. When hit is not None, safe_to_emit
        contains everything strictly before the stop sequence.
        """
        if self._done:
            return "", None
        combined = self._buf + chunk
        # Look for earliest hit of any stop sequence.
        earliest: Optional[Tuple[int, str]] = None
        for s in self._stops:
            i = combined.find(s)
            if i == -1:
                continue
            if earliest is None or i < earliest[0]:
                earliest = (i, s)
        if earliest is not None:
            idx, s = earliest
            emit = combined[:idx]
            self._buf = ""
            self._done = True
            return emit, (s, idx)
        # No hit: keep tail of size (max_len - 1) so a boundary-spanning match
        # in the next chunk is still detectable.
        keep = self._max_len - 1
        if keep <= 0 or len(combined) <= keep:
            self._buf = combined
            return "", None
        emit = combined[:-keep]
        self._buf = combined[-keep:]
        return emit, None

    def flush(self) -> str:
        """Stream ended without a stop hit; return any buffered tail."""
        if self._done:
            return ""
        out = self._buf
        self._buf = ""
        self._done = True
        return out

    @property
    def done(self) -> bool:
        return self._done
