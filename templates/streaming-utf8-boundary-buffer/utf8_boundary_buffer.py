"""streaming-utf8-boundary-buffer — stdlib-only reference.

Hold back a partial trailing UTF-8 sequence at chunk boundaries so a streamed
byte stream (SSE / HTTP / pipe) never emits half a codepoint to a downstream
text consumer.

The bug this prevents:
    chunk_a = b"hello \xe4\xb8"          # first 2 bytes of 3-byte 中
    chunk_b = b"\xad world"               # last byte of 中, then " world"
    naive  = chunk_a.decode("utf-8") + chunk_b.decode("utf-8")
            # UnicodeDecodeError on chunk_a, OR replacement chars if errors="replace"

The fix is structural, not statistical: UTF-8 is self-synchronizing and the
length of a multibyte sequence is encoded in the leading byte. We can compute
exactly how many trailing bytes might still be the start of a valid codepoint
(0..3) and hold *only* those back for the next chunk.

API:
    Utf8BoundaryBuffer()
        .feed(chunk: bytes) -> str        # decoded text safe to emit now
        .flush() -> str                   # call once at EOF; raises if invalid
        .pending_bytes -> int             # how many bytes are held back
        .total_emitted_chars -> int       # observability
"""

from __future__ import annotations

from dataclasses import dataclass, field


class Utf8BoundaryError(ValueError):
    """Raised on flush() when held-back bytes are not a valid UTF-8 prefix."""


def _trailing_partial_len(buf: bytes) -> int:
    """How many trailing bytes of `buf` look like the start of an incomplete
    UTF-8 sequence?

    Returns 0..3. Returns 0 if the trailing bytes form a complete codepoint
    or are continuation bytes for one that started further back than we'd
    consider partial (we cap at 3 since UTF-8 codepoints are at most 4 bytes).

    UTF-8 leading byte shapes:
        0xxxxxxx              -> 1-byte codepoint, complete
        110xxxxx 10xxxxxx     -> 2-byte
        1110xxxx 10xxxxxx*2   -> 3-byte
        11110xxx 10xxxxxx*3   -> 4-byte
    """
    n = len(buf)
    # Walk back up to 3 bytes looking for a leading byte (non-continuation).
    # Continuation bytes have the top two bits == 10 (0x80..0xBF).
    for back in range(1, min(4, n) + 1):
        b = buf[n - back]
        if (b & 0xC0) == 0x80:
            # Continuation byte; keep walking back.
            continue
        # Found the leading byte of the trailing sequence.
        if (b & 0x80) == 0x00:
            expected = 1
        elif (b & 0xE0) == 0xC0:
            expected = 2
        elif (b & 0xF0) == 0xE0:
            expected = 3
        elif (b & 0xF8) == 0xF0:
            expected = 4
        else:
            # Invalid leading byte — leave it in the buffer; flush() will
            # surface it. Returning 0 means "do not hold anything back",
            # which forces the decoder on the *next* feed() to see this
            # invalid byte and raise. We prefer raise-loudly over hide.
            return 0
        if back >= expected:
            # The trailing sequence is complete.
            return 0
        # The trailing sequence is incomplete; hold back `back` bytes.
        return back
    # All trailing bytes (up to 3) were continuation bytes with no leading
    # byte found — definitely malformed; let the decoder surface it.
    return 0


@dataclass
class Utf8BoundaryBuffer:
    _buf: bytearray = field(default_factory=bytearray)
    total_emitted_chars: int = 0
    total_fed_bytes: int = 0

    @property
    def pending_bytes(self) -> int:
        return len(self._buf)

    def feed(self, chunk: bytes) -> str:
        """Append `chunk`, decode and return the largest UTF-8 prefix that is
        complete; retain a 0..3 byte tail for the next call.
        """
        if not isinstance(chunk, (bytes, bytearray)):
            raise TypeError(f"feed() expects bytes, got {type(chunk).__name__}")
        self.total_fed_bytes += len(chunk)
        self._buf.extend(chunk)
        hold = _trailing_partial_len(bytes(self._buf))
        if hold == 0:
            emit = bytes(self._buf)
            self._buf.clear()
        else:
            emit = bytes(self._buf[:-hold])
            del self._buf[:-hold]
        # Use strict decode here — if a *complete* prefix is invalid, that is
        # a real wire error and the caller deserves to see it immediately,
        # not at flush() time when the offending bytes are far behind us.
        text = emit.decode("utf-8")
        self.total_emitted_chars += len(text)
        return text

    def flush(self) -> str:
        """Final flush at EOF. Raises Utf8BoundaryError if held-back bytes
        are not a valid (now-completed) UTF-8 sequence — i.e. the stream
        actually ended on a torn codepoint.
        """
        if not self._buf:
            return ""
        try:
            text = bytes(self._buf).decode("utf-8")
        except UnicodeDecodeError as e:
            held = bytes(self._buf)
            self._buf.clear()
            raise Utf8BoundaryError(
                f"stream ended with {len(held)} byte(s) of incomplete utf-8: "
                f"{held!r} ({e.reason})"
            ) from None
        self._buf.clear()
        self.total_emitted_chars += len(text)
        return text
