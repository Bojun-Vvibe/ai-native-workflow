"""Streaming chunk reassembler.

Pure, stdlib-only reference engine for reassembling an LLM (or any
producer's) streamed token/byte chunks into the original ordered stream
when the transport may deliver chunks **out of order**, **duplicated**,
or with **gaps**.

API contract
------------
- A chunk is a dict: {"seq": int, "data": str, "is_final": bool}
- `seq` starts at 0 and increments by 1; gaps mean missing chunks.
- A reassembler instance is single-stream; create one per stream.
- `accept(chunk)` returns a list of chunks that became deliverable in
  arrival order, i.e. all consecutive `next_seq, next_seq+1, ...`
  chunks that are now available because the missing prefix arrived.
- `accept` is idempotent on duplicate `seq` (with byte-equal `data`);
  a duplicate with a *different* payload raises `InconsistentChunk`.
- `state()` returns a snapshot dict (deterministic ordering of fields)
  describing what has been delivered, what is buffered, and what gaps
  remain — suitable for a heartbeat/log line.
- `is_complete()` returns True iff a chunk with `is_final=True` has
  been delivered AND no gaps remain before its `seq`.

Invariants
----------
1. A chunk is delivered AT MOST ONCE (no double delivery on duplicate).
2. Chunks are delivered in strict `seq` order (caller can concatenate
   `data` directly).
3. The buffer never holds a chunk whose `seq < next_expected_seq`
   (those have already been delivered).
4. `is_final` cannot move backward: if a chunk with `is_final=True`
   at seq=N has been observed, accepting `is_final=True` at any other
   seq raises `InconsistentChunk`.

Out of scope
------------
- No I/O, no timeouts, no retransmit requests. The caller decides when
  to give up on a gap (see `gap_seqs()` for the missing list).
"""

from __future__ import annotations

from typing import Any


class InconsistentChunk(ValueError):
    """A chunk contradicts a previously accepted chunk."""


class StreamReassembler:
    def __init__(self) -> None:
        self._next_expected: int = 0
        self._buffer: dict[int, dict[str, Any]] = {}
        # Track every seq we've ever accepted (for duplicate detection)
        # by keeping its bytes, even after delivery.
        self._seen: dict[int, str] = {}
        self._final_seq: int | None = None
        self._delivered_count: int = 0

    # ---- public API -----------------------------------------------------

    def accept(self, chunk: dict[str, Any]) -> list[dict[str, Any]]:
        self._validate_shape(chunk)
        seq = chunk["seq"]
        data = chunk["data"]
        is_final = chunk["is_final"]

        # Duplicate detection (covers both already-delivered and buffered).
        if seq in self._seen:
            if self._seen[seq] != data:
                raise InconsistentChunk(
                    f"seq={seq} arrived twice with different payload"
                )
            # Idempotent duplicate: nothing new to deliver.
            return []

        # is_final consistency
        if is_final:
            if self._final_seq is not None and self._final_seq != seq:
                raise InconsistentChunk(
                    f"is_final already set at seq={self._final_seq}, "
                    f"cannot re-set at seq={seq}"
                )
            self._final_seq = seq

        self._seen[seq] = data

        if seq < self._next_expected:
            # Late arrival of a seq we already delivered? That would have
            # been caught by the duplicate check above. Reaching here
            # means we somehow have an unseen-but-too-old seq; that's a
            # bug in the caller, not us. Treat as inconsistent.
            raise InconsistentChunk(
                f"seq={seq} is below next_expected={self._next_expected} "
                f"and was not previously seen"
            )

        self._buffer[seq] = chunk
        return self._drain()

    def state(self) -> dict[str, Any]:
        return {
            "next_expected_seq": self._next_expected,
            "delivered_count": self._delivered_count,
            "buffered_seqs": sorted(self._buffer.keys()),
            "gap_seqs": self.gap_seqs(),
            "final_seq": self._final_seq,
            "is_complete": self.is_complete(),
        }

    def gap_seqs(self) -> list[int]:
        """Return the sorted list of missing seqs between
        `next_expected_seq` and the highest buffered/seen seq."""
        if not self._buffer:
            return []
        highest = max(self._buffer.keys())
        return [s for s in range(self._next_expected, highest)
                if s not in self._buffer]

    def is_complete(self) -> bool:
        if self._final_seq is None:
            return False
        # All chunks 0 .. final_seq must have been delivered.
        return self._next_expected > self._final_seq

    # ---- internals ------------------------------------------------------

    def _validate_shape(self, chunk: dict[str, Any]) -> None:
        if not isinstance(chunk, dict):
            raise TypeError("chunk must be a dict")
        for k in ("seq", "data", "is_final"):
            if k not in chunk:
                raise ValueError(f"chunk missing required field: {k}")
        if not isinstance(chunk["seq"], int) or chunk["seq"] < 0:
            raise ValueError(f"seq must be a non-negative int, got {chunk['seq']!r}")
        if not isinstance(chunk["data"], str):
            raise ValueError("data must be a str")
        if not isinstance(chunk["is_final"], bool):
            raise ValueError("is_final must be a bool")

    def _drain(self) -> list[dict[str, Any]]:
        delivered: list[dict[str, Any]] = []
        while self._next_expected in self._buffer:
            ch = self._buffer.pop(self._next_expected)
            delivered.append(ch)
            self._next_expected += 1
            self._delivered_count += 1
        return delivered
