#!/usr/bin/env python3
"""Debounce-style batching window for tool calls.

Many tool surfaces have a *bulk* form that costs roughly the same as a
single-item form (e.g. `read_files([…])` vs N separate `read_file`
calls; `vector_lookup([…])` vs N point lookups). When an agent loop
emits N small calls in a tight burst, paying N round-trip costs is
strictly worse than paying one bulk-call cost — provided the caller
can tolerate a small wait.

This template is the batching window that *enables* that swap. The
agent calls `submit(args)`; the window holds the call for up to
`max_wait_s` (or until `max_batch_size` is reached) and then flushes
all pending calls to a caller-supplied `bulk_fn`. Each `submit` returns
a small `Pending` handle the caller resolves after `tick(now_s)`
flushes the batch.

Design rules:

  - **No background threads.** Pure value-object. Caller drives time
    by calling `tick(now_s)` (in a loop, on a frame, on a heartbeat).
    Deterministic, testable, framework-agnostic.
  - **Two flush triggers, OR-ed:** size cap (`max_batch_size`) trips
    immediately on `submit`; deadline (`max_wait_s` since first item)
    trips on the next `tick`. Whichever fires first wins.
  - **Deadline measured from the *first* item**, not the most recent.
    A trickle of one item every (max_wait_s − ε) must NOT defer the
    flush forever. (This is the bug almost every naive debouncer has.)
  - **Order preservation.** The bulk_fn receives args in submit-order;
    its return list is mapped back by index. A `bulk_fn` that returns
    a wrong-length list raises `BatchSizeMismatch` — better a loud
    failure than silently misattributing results.
  - **bulk_fn errors fan out.** If `bulk_fn` raises, every pending
    handle in that flush is resolved with the same exception. The
    batch is not retried automatically — that is the caller's policy
    (compose with `tool-call-retry-envelope`).
  - **flush() drains synchronously**, even mid-window. Useful in
    shutdown paths and in `streaming-cancellation-token` cleanups.
  - **No partial flushes.** A flush is all-or-nothing across the
    pending list. Avoids the "which 3 of 5 already went?" bookkeeping
    nightmare.

Pure stdlib. Caller injects clock and `bulk_fn`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, List, Optional


class BatchSizeMismatch(Exception):
    """`bulk_fn` returned a list of the wrong length for the batch."""


class WindowClosed(Exception):
    """`submit` called after `close()`."""


@dataclass
class Pending:
    """Per-call handle. Resolved after the batch flushes."""
    index_in_batch: int = -1
    batch_id: int = -1
    _resolved: bool = False
    _result: Any = None
    _error: Optional[BaseException] = None

    @property
    def resolved(self) -> bool:
        return self._resolved

    def result(self) -> Any:
        if not self._resolved:
            raise RuntimeError("Pending not yet resolved; tick the window")
        if self._error is not None:
            raise self._error
        return self._result


@dataclass
class BatchingWindow:
    """Debounce-window batcher.

    `bulk_fn(args_list) -> results_list` MUST return a list with the
    same length as `args_list`, in the same order.
    """
    bulk_fn: Callable[[List[Any]], List[Any]]
    max_wait_s: float
    max_batch_size: int

    _pending_args: List[Any] = field(default_factory=list, init=False)
    _pending_handles: List[Pending] = field(default_factory=list, init=False)
    _first_submit_s: Optional[float] = field(default=None, init=False)
    _next_batch_id: int = field(default=0, init=False)
    _closed: bool = field(default=False, init=False)
    _stats_flushes: int = field(default=0, init=False)
    _stats_size_trips: int = field(default=0, init=False)
    _stats_deadline_trips: int = field(default=0, init=False)
    _stats_manual_flushes: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        if self.max_wait_s < 0:
            raise ValueError("max_wait_s must be >= 0")
        if self.max_batch_size < 1:
            raise ValueError("max_batch_size must be >= 1")

    # --- producer side -------------------------------------------------

    def submit(self, args: Any, now_s: float) -> Pending:
        """Queue an item. May trigger an immediate size-cap flush."""
        if self._closed:
            raise WindowClosed("window is closed; submit rejected")
        handle = Pending()
        self._pending_args.append(args)
        self._pending_handles.append(handle)
        if self._first_submit_s is None:
            self._first_submit_s = now_s
        if len(self._pending_args) >= self.max_batch_size:
            self._stats_size_trips += 1
            self._flush(now_s, trigger="size_cap")
        return handle

    # --- driver side ---------------------------------------------------

    def tick(self, now_s: float) -> int:
        """Advance the clock. Returns number of items flushed (0 if not yet)."""
        if self._first_submit_s is None:
            return 0
        elapsed = now_s - self._first_submit_s
        if elapsed >= self.max_wait_s:
            n = len(self._pending_args)
            self._stats_deadline_trips += 1
            self._flush(now_s, trigger="deadline")
            return n
        return 0

    def flush(self, now_s: float) -> int:
        """Drain immediately. Returns number of items flushed."""
        if self._first_submit_s is None:
            return 0
        n = len(self._pending_args)
        self._stats_manual_flushes += 1
        self._flush(now_s, trigger="manual")
        return n

    def close(self, now_s: float) -> None:
        """Drain and refuse further submits."""
        if self._first_submit_s is not None:
            self.flush(now_s)
        self._closed = True

    # --- internals -----------------------------------------------------

    def _flush(self, now_s: float, trigger: str) -> None:
        args_list = self._pending_args
        handles = self._pending_handles
        batch_id = self._next_batch_id
        self._next_batch_id += 1
        # Reset state BEFORE calling bulk_fn so that a re-entrant submit
        # from within bulk_fn (rare but possible) starts a new window.
        self._pending_args = []
        self._pending_handles = []
        self._first_submit_s = None
        self._stats_flushes += 1

        for i, h in enumerate(handles):
            h.index_in_batch = i
            h.batch_id = batch_id

        try:
            results = self.bulk_fn(args_list)
        except BaseException as exc:  # noqa: BLE001
            for h in handles:
                h._error = exc
                h._resolved = True
            return

        if not isinstance(results, list) or len(results) != len(args_list):
            err = BatchSizeMismatch(
                f"bulk_fn returned {type(results).__name__} of "
                f"len={len(results) if hasattr(results, '__len__') else '?'}; "
                f"expected list of len={len(args_list)}"
            )
            for h in handles:
                h._error = err
                h._resolved = True
            return

        for h, r in zip(handles, results):
            h._result = r
            h._resolved = True

    # --- introspection -------------------------------------------------

    def state(self) -> dict:
        return {
            "closed": self._closed,
            "deadline_trips": self._stats_deadline_trips,
            "first_submit_s": self._first_submit_s,
            "flushes_total": self._stats_flushes,
            "manual_flushes": self._stats_manual_flushes,
            "pending_count": len(self._pending_args),
            "size_trips": self._stats_size_trips,
        }
