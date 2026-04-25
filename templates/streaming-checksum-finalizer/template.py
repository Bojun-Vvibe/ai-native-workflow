"""Streaming checksum finalizer.

Incrementally hashes a stream of chunks and yields a *final* digest only when
the stream is explicitly closed via `finalize()`. Reading `.digest` mid-stream
returns ``None`` — never a partial-but-plausible-looking hex string that a
downstream consumer might mistake for the real one.

Design rules:

- Hash work happens incrementally on every ``feed`` (constant memory).
- ``digest`` and ``hexdigest`` are ``None`` until ``finalize()`` is called.
- ``finalize()`` is idempotent: calling it twice returns the same digest and
  does not re-hash.
- After ``finalize()``, additional ``feed()`` calls raise ``StreamClosedError``
  so a late chunk cannot silently corrupt the recorded hash.
- ``abort()`` marks the stream poisoned; ``digest`` stays ``None`` forever and
  any later ``feed`` / ``finalize`` raises ``StreamAbortedError``. Callers
  never see a digest for a stream that was cancelled or errored mid-flight.
- ``bytes_seen`` is exposed so a caller can cross-check against a declared
  ``Content-Length`` before trusting the digest.

Stdlib-only. Default algorithm sha256; any name accepted by ``hashlib.new``
also works.
"""

from __future__ import annotations

import hashlib
from typing import Optional, Union


class StreamClosedError(RuntimeError):
    """Raised when feed() is called after finalize()."""


class StreamAbortedError(RuntimeError):
    """Raised when feed() or finalize() is called on an aborted stream."""


class ChecksumFinalizer:
    def __init__(self, algorithm: str = "sha256") -> None:
        # hashlib.new validates the algorithm name; raises ValueError if bad.
        self._h = hashlib.new(algorithm)
        self._algorithm = algorithm
        self._bytes_seen = 0
        self._final_digest: Optional[bytes] = None
        self._final_hex: Optional[str] = None
        self._aborted = False
        self._closed = False

    @property
    def algorithm(self) -> str:
        return self._algorithm

    @property
    def bytes_seen(self) -> int:
        return self._bytes_seen

    @property
    def closed(self) -> bool:
        return self._closed

    @property
    def aborted(self) -> bool:
        return self._aborted

    @property
    def digest(self) -> Optional[bytes]:
        """Final raw digest, or None if the stream is not yet finalized."""
        return self._final_digest

    @property
    def hexdigest(self) -> Optional[str]:
        """Final hex digest, or None if the stream is not yet finalized."""
        return self._final_hex

    def feed(self, chunk: Union[bytes, bytearray, memoryview]) -> None:
        if self._aborted:
            raise StreamAbortedError("stream was aborted; further input rejected")
        if self._closed:
            raise StreamClosedError("stream already finalized; further input rejected")
        if not isinstance(chunk, (bytes, bytearray, memoryview)):
            raise TypeError(f"feed() expects bytes-like, got {type(chunk).__name__}")
        # memoryview / bytearray are accepted by hashlib.update directly.
        self._h.update(chunk)
        self._bytes_seen += len(chunk)

    def finalize(self) -> str:
        """Close the stream and return the final hex digest.

        Idempotent: calling twice returns the same hex string without
        re-hashing. Raises StreamAbortedError if the stream was aborted.
        """
        if self._aborted:
            raise StreamAbortedError("cannot finalize an aborted stream")
        if self._closed:
            assert self._final_hex is not None  # established by previous call
            return self._final_hex
        self._final_digest = self._h.digest()
        self._final_hex = self._h.hexdigest()
        self._closed = True
        return self._final_hex

    def abort(self) -> None:
        """Poison the stream; no digest will ever be produced."""
        # Idempotent: aborting twice is a no-op.
        self._aborted = True
        # Drop hasher reference so a buggy caller can't sneak more input in.
        self._final_digest = None
        self._final_hex = None
