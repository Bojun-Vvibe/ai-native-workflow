"""Periodic checkpoint of streaming output so a kill mid-flight leaves
recoverable state.

Use case: an LLM is streaming a long structured output (or a tool is
streaming a large file/render/log). If the host dies mid-stream, the
caller wants to resume from the last *durable* boundary, not from
scratch and not from a half-written byte.

The Checkpointer:
  - accepts incremental chunks via `append(chunk)`,
  - flushes to a writer (passed in) at boundaries chosen by `policy`
    (every N bytes OR every N seconds, whichever fires first),
  - records each flush as a single JSONL record with a running
    SHA-256 of the bytes written so far,
  - exposes `recover(records)` which replays a JSONL log and returns
    the byte offset + content hash of the last *complete* record so
    the caller can seek the underlying sink and resume.

The contract is: a record on disk means the bytes for that checkpoint
are durable. A torn final record (truncated JSON line) is ignored on
recover — the caller resumes from the previous good record.

Stdlib only. Pure: writer and clock are injected.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Callable


class CheckpointError(RuntimeError):
    """Raised on misuse (double-finalize, append-after-finalize)."""


@dataclass(frozen=True)
class FlushPolicy:
    every_bytes: int  # flush when buffered >= this
    every_seconds: float  # flush when (now - last_flush_at) >= this

    def __post_init__(self) -> None:
        if self.every_bytes <= 0:
            raise ValueError("every_bytes must be > 0")
        if self.every_seconds <= 0:
            raise ValueError("every_seconds must be > 0")


@dataclass
class Checkpointer:
    stream_id: str
    policy: FlushPolicy
    sink_write: Callable[[bytes], None]  # underlying durable byte sink (file, etc.)
    log_write: Callable[[str], None]  # JSONL log appender (one line per flush)
    now_fn: Callable[[], float]
    _buf: bytearray = field(default_factory=bytearray)
    _bytes_committed: int = 0
    _hash: "hashlib._Hash" = field(default_factory=lambda: hashlib.sha256())
    _last_flush_at: float = 0.0
    _seq: int = 0
    _finalized: bool = False

    def __post_init__(self) -> None:
        self._last_flush_at = self.now_fn()

    def append(self, chunk: bytes) -> int:
        """Buffer a chunk; flush if policy says so. Returns flush count
        triggered by this call (0 or 1)."""
        if self._finalized:
            raise CheckpointError("append after finalize")
        if not isinstance(chunk, (bytes, bytearray)):
            raise TypeError("chunk must be bytes")
        self._buf.extend(chunk)
        if self._should_flush():
            self._flush(reason="policy")
            return 1
        return 0

    def _should_flush(self) -> bool:
        if len(self._buf) >= self.policy.every_bytes:
            return True
        if (self.now_fn() - self._last_flush_at) >= self.policy.every_seconds:
            return len(self._buf) > 0  # don't flush empty
        return False

    def _flush(self, reason: str) -> None:
        if not self._buf and reason != "finalize":
            return
        payload = bytes(self._buf)
        self.sink_write(payload)
        self._hash.update(payload)
        self._bytes_committed += len(payload)
        self._buf.clear()
        self._last_flush_at = self.now_fn()
        record = {
            "stream_id": self.stream_id,
            "seq": self._seq,
            "bytes_committed": self._bytes_committed,
            "chunk_bytes": len(payload),
            "running_sha256": self._hash.hexdigest(),
            "flushed_at": round(self._last_flush_at, 6),
            "reason": reason,
        }
        # Single newline-terminated JSON object — atomic on POSIX up to
        # PIPE_BUF for small records, and torn-record-detectable on
        # recover.
        self.log_write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
        self._seq += 1

    def finalize(self) -> dict:
        if self._finalized:
            raise CheckpointError("already finalized")
        self._flush(reason="finalize")
        self._finalized = True
        return {
            "stream_id": self.stream_id,
            "bytes_committed": self._bytes_committed,
            "final_sha256": self._hash.hexdigest(),
            "checkpoints": self._seq,
        }

    def state(self) -> dict:
        return {
            "stream_id": self.stream_id,
            "bytes_buffered": len(self._buf),
            "bytes_committed": self._bytes_committed,
            "checkpoints": self._seq,
            "finalized": self._finalized,
        }


@dataclass
class RecoveryPlan:
    stream_id: str | None
    bytes_committed: int
    last_running_sha256: str | None
    intact_records: int
    torn_trailing_record: bool

    def to_dict(self) -> dict:
        return {
            "stream_id": self.stream_id,
            "bytes_committed": self.bytes_committed,
            "last_running_sha256": self.last_running_sha256,
            "intact_records": self.intact_records,
            "torn_trailing_record": self.torn_trailing_record,
        }


def recover(log_text: str, expected_stream_id: str | None = None) -> RecoveryPlan:
    """Parse a checkpoint log and return the resume point.

    A line that fails JSON parse is treated as a torn write (host died
    mid-flush) and ignored — the caller resumes from the previous good
    record. A line whose `stream_id` does not match
    `expected_stream_id` raises `CheckpointError` (mixed logs).

    Returns the byte offset and SHA-256 the caller should seek/verify
    on the underlying sink before resuming.
    """
    intact: list[dict] = []
    torn = False
    lines = log_text.splitlines(keepends=False)
    for i, line in enumerate(lines):
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            # Only the trailing record is allowed to be torn.
            if i == len(lines) - 1:
                torn = True
                continue
            raise CheckpointError(f"torn record at line {i} (not trailing)")
        if expected_stream_id is not None and rec.get("stream_id") != expected_stream_id:
            raise CheckpointError(
                f"stream_id mismatch at line {i}: "
                f"expected {expected_stream_id!r}, got {rec.get('stream_id')!r}"
            )
        intact.append(rec)

    if not intact:
        return RecoveryPlan(
            stream_id=expected_stream_id,
            bytes_committed=0,
            last_running_sha256=None,
            intact_records=0,
            torn_trailing_record=torn,
        )
    last = intact[-1]
    # Sanity: seqs are dense and start at 0
    expected_seqs = list(range(len(intact)))
    actual_seqs = [r["seq"] for r in intact]
    if actual_seqs != expected_seqs:
        raise CheckpointError(f"non-dense seqs in log: {actual_seqs}")
    return RecoveryPlan(
        stream_id=last["stream_id"],
        bytes_committed=last["bytes_committed"],
        last_running_sha256=last["running_sha256"],
        intact_records=len(intact),
        torn_trailing_record=torn,
    )
