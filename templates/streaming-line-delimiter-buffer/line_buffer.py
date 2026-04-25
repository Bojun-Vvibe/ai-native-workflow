"""Line-delimited stream buffer for NDJSON / SSE-data-line / log-tail streams.

Problem: bytes arrive in arbitrarily-sized chunks (TLS frames, HTTP/2
DATA frames, kernel pipe writes). A line-oriented consumer (NDJSON
parser, SSE event splitter, log shipper) must NEVER see a half-line
because parsing it would either crash or — worse — silently corrupt
state. The trailing partial line of chunk N is the prefix of the first
line of chunk N+1, except when the stream ends without a final newline,
in which case it is itself a complete record (or it is garbage and the
caller asked us to be strict).

Contract:
  buf = LineBuffer(delimiter=b"\\n", max_line_bytes=1_048_576,
                   strict_trailing=False)
  for chunk in stream:
      for line in buf.feed(chunk):
          handle(line)            # bytes, delimiter stripped
  for line in buf.close():        # flush any trailing partial record
      handle(line)

Invariants (the kind of invariants you want unit-tested before shipping):
  * `feed` never returns a partial line.
  * Two delimiters in different chunks (e.g. b"\\r" then b"\\n" for CRLF)
    are joined correctly when delimiter=b"\\r\\n".
  * `feed(b"")` is a no-op (returns []), not a "stream ended" signal.
    `close()` is the only stream-end signal.
  * A single line longer than `max_line_bytes` raises `LineTooLong`
    BEFORE the closing delimiter arrives — we don't let an attacker
    pin unbounded memory waiting for a delimiter that never comes.
  * After `close()`, further `feed`/`close` calls raise `BufferClosed`.
  * `strict_trailing=True` and a non-empty unterminated tail at close
    raises `UnterminatedTrailingLine` instead of yielding it.

Stdlib only. No async, no I/O — the caller owns the transport.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


class LineBufferError(Exception):
    """Base class so callers can `except LineBufferError`."""


class LineTooLong(LineBufferError):
    def __init__(self, observed_bytes: int, limit: int):
        super().__init__(
            f"line exceeded max_line_bytes: observed {observed_bytes} > limit {limit}"
        )
        self.observed_bytes = observed_bytes
        self.limit = limit


class UnterminatedTrailingLine(LineBufferError):
    def __init__(self, length: int):
        super().__init__(
            f"stream closed with {length}-byte unterminated trailing line under strict_trailing=True"
        )
        self.length = length


class BufferClosed(LineBufferError):
    pass


@dataclass
class LineBuffer:
    delimiter: bytes = b"\n"
    max_line_bytes: int = 1 << 20  # 1 MiB
    strict_trailing: bool = False
    _buf: bytearray = field(default_factory=bytearray)
    _closed: bool = False

    def __post_init__(self) -> None:
        if not self.delimiter:
            raise ValueError("delimiter must be non-empty")
        if self.max_line_bytes < 1:
            raise ValueError("max_line_bytes must be >= 1")

    # ---------- public API ----------

    def feed(self, chunk: bytes) -> List[bytes]:
        if self._closed:
            raise BufferClosed("feed() after close()")
        if not chunk:
            return []
        self._buf.extend(chunk)
        return self._drain()

    def close(self) -> List[bytes]:
        if self._closed:
            raise BufferClosed("close() called twice")
        self._closed = True
        out = self._drain()
        if self._buf:
            tail = bytes(self._buf)
            self._buf.clear()
            if self.strict_trailing:
                raise UnterminatedTrailingLine(len(tail))
            out.append(tail)
        return out

    @property
    def pending_bytes(self) -> int:
        """Bytes buffered waiting for a delimiter. Useful for backpressure."""
        return len(self._buf)

    @property
    def closed(self) -> bool:
        return self._closed

    # ---------- internals ----------

    def _drain(self) -> List[bytes]:
        out: List[bytes] = []
        d = self.delimiter
        dlen = len(d)
        while True:
            idx = self._buf.find(d)
            if idx == -1:
                # No complete line. If what's left already exceeds the
                # cap (and there's no delimiter in sight) we MUST fail
                # now — waiting for one would let a malicious stream
                # OOM us.
                if len(self._buf) > self.max_line_bytes:
                    observed = len(self._buf)
                    self._buf.clear()
                    raise LineTooLong(observed, self.max_line_bytes)
                return out
            line = bytes(self._buf[:idx])
            if len(line) > self.max_line_bytes:
                observed = len(line)
                # Drop the offender so the next drain doesn't loop.
                del self._buf[: idx + dlen]
                raise LineTooLong(observed, self.max_line_bytes)
            out.append(line)
            del self._buf[: idx + dlen]
