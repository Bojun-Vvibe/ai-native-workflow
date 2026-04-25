"""embedding-batch-coalescer — stdlib-only reference.

Coalesces concurrent single-item embedding requests into batched calls.

Submit one text at a time; get back a Future. The coalescer waits up to
`max_wait_s` for more items to arrive, then flushes a batch of up to
`max_batch_size` items in one underlying call. Each future is resolved
with its own embedding (or raised exception) once the batch returns.

Design constraints:
  * stdlib only (threading, queue, time, dataclasses)
  * the embed_fn the caller passes is a *batch* function:
        embed_fn(List[str]) -> List[List[float]]
  * dedup: identical strings inside one batch share one upstream slot
  * exceptions from embed_fn propagate to *every* future in that batch
  * graceful shutdown: close() flushes pending items, then joins
"""

from __future__ import annotations

import threading
import time
from concurrent.futures import Future
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Sequence

EmbedFn = Callable[[Sequence[str]], List[List[float]]]


@dataclass
class _Pending:
    text: str
    future: "Future[List[float]]"
    submitted_at: float


@dataclass
class CoalescerStats:
    submitted: int = 0
    batches_flushed: int = 0
    items_in_batches: int = 0
    upstream_calls: int = 0
    upstream_items: int = 0  # items actually sent (after dedup)
    flushed_by_size: int = 0
    flushed_by_time: int = 0
    flushed_by_close: int = 0
    errors: int = 0


@dataclass
class _State:
    pending: List[_Pending] = field(default_factory=list)
    closed: bool = False


class EmbeddingBatchCoalescer:
    """Background-thread coalescer.

    Thread-safe. One coalescer per upstream model is the typical shape.
    """

    def __init__(
        self,
        embed_fn: EmbedFn,
        *,
        max_batch_size: int = 64,
        max_wait_s: float = 0.05,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if max_batch_size < 1:
            raise ValueError("max_batch_size must be >= 1")
        if max_wait_s < 0:
            raise ValueError("max_wait_s must be >= 0")
        self._embed_fn = embed_fn
        self._max_batch_size = max_batch_size
        self._max_wait_s = max_wait_s
        self._clock = clock
        self._state = _State()
        self._lock = threading.Lock()
        self._wake = threading.Condition(self._lock)
        self.stats = CoalescerStats()
        self._thread = threading.Thread(
            target=self._run, name="EmbeddingBatchCoalescer", daemon=True
        )
        self._thread.start()

    # --- public API ---------------------------------------------------

    def submit(self, text: str) -> "Future[List[float]]":
        fut: "Future[List[float]]" = Future()
        with self._wake:
            if self._state.closed:
                fut.set_exception(RuntimeError("coalescer is closed"))
                return fut
            self._state.pending.append(_Pending(text, fut, self._clock()))
            self.stats.submitted += 1
            self._wake.notify()
        return fut

    def close(self, timeout: Optional[float] = None) -> None:
        with self._wake:
            self._state.closed = True
            self._wake.notify_all()
        self._thread.join(timeout=timeout)

    # --- worker loop --------------------------------------------------

    def _run(self) -> None:
        while True:
            with self._wake:
                # Wait for first item or close.
                while not self._state.pending and not self._state.closed:
                    self._wake.wait()
                if not self._state.pending and self._state.closed:
                    return
                first_arrival = self._state.pending[0].submitted_at
                # Wait until the window closes OR batch is full OR closed.
                while True:
                    if self._state.closed:
                        flush_reason = "close"
                        break
                    if len(self._state.pending) >= self._max_batch_size:
                        flush_reason = "size"
                        break
                    elapsed = self._clock() - first_arrival
                    remaining = self._max_wait_s - elapsed
                    if remaining <= 0:
                        flush_reason = "time"
                        break
                    self._wake.wait(timeout=remaining)
                # Atomically take the batch under the lock.
                batch = self._state.pending[: self._max_batch_size]
                self._state.pending = self._state.pending[self._max_batch_size :]
            self._flush(batch, flush_reason)

    def _flush(self, batch: List[_Pending], reason: str) -> None:
        if not batch:
            return
        self.stats.batches_flushed += 1
        self.stats.items_in_batches += len(batch)
        if reason == "size":
            self.stats.flushed_by_size += 1
        elif reason == "time":
            self.stats.flushed_by_time += 1
        else:
            self.stats.flushed_by_close += 1

        # Dedup: identical text -> one upstream slot.
        unique: List[str] = []
        index_of: dict[str, int] = {}
        per_item_idx: List[int] = []
        for p in batch:
            idx = index_of.get(p.text)
            if idx is None:
                idx = len(unique)
                index_of[p.text] = idx
                unique.append(p.text)
            per_item_idx.append(idx)

        try:
            self.stats.upstream_calls += 1
            self.stats.upstream_items += len(unique)
            results = self._embed_fn(unique)
            if len(results) != len(unique):
                raise RuntimeError(
                    f"embed_fn returned {len(results)} embeddings for "
                    f"{len(unique)} inputs"
                )
        except BaseException as exc:  # noqa: BLE001 - propagate to all futures
            self.stats.errors += 1
            for p in batch:
                if not p.future.done():
                    p.future.set_exception(exc)
            return

        for p, idx in zip(batch, per_item_idx):
            if not p.future.done():
                p.future.set_result(results[idx])
