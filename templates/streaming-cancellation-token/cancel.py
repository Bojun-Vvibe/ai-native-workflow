#!/usr/bin/env python3
"""Cooperative cancellation token for streaming agent calls.

A streamed model call (or streamed tool call) cannot just be killed
mid-flight: there are partial bytes in flight, downstream side effects
already begun (a tool that opened a file, a UI that showed half a
message), and a cost meter that has already debited tokens. A `kill -9`
on the producer leaks all of that.

This template offers the *cooperative* alternative: a small token the
producer checks at every yield boundary. When `cancel(reason)` is
called, the producer observes it on the next check, runs registered
cleanup callbacks in LIFO order, and raises `Cancelled` so the caller
gets a structured stop instead of a half-stream.

Design rules (the boring kind that matter):

  - Cancellation is `set-once`. Calling `cancel("a")` then `cancel("b")`
    keeps `"a"`. The first reason wins so audit logs are stable.
  - Cleanups run LIFO. They were registered in dependency order
    (open-file before write-temp before flush-buffer), so they have to
    tear down in the reverse order or you get use-after-free in glue
    code.
  - A cleanup that raises does NOT abort the rest. Each cleanup's
    exception is captured into `cleanup_errors` and the *next* cleanup
    runs anyway. Half-cleanup is worse than slow-cleanup.
  - Cleanups run at most once. If `run_cleanups()` is called twice
    (e.g. producer's `finally` + caller's belt-and-suspenders), the
    second call is a no-op.
  - `register_cleanup` after cancel runs the cleanup *immediately* and
    captures any error — otherwise a late-registered handler would
    silently leak its resource.
  - This module does NO I/O, no threads, no asyncio. The caller decides
    *how* the producer is driven; the token is a pure value-object.

Pure stdlib. Deterministic. No clocks involved (cancel is event-driven,
not deadline-driven — see `tool-call-timeout-laddered` for deadlines).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, List, Optional, Tuple


class Cancelled(Exception):
    """Raised by `raise_if_cancelled()` when the token is tripped."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass
class CancellationToken:
    """Cooperative cancellation handle.

    Producers poll `is_cancelled()` / `raise_if_cancelled()` at every
    yield boundary. Consumers call `cancel(reason)` once. Cleanups are
    registered by whoever opens a resource and run on first cancel or
    on producer `finally`-side `run_cleanups()`.

    Fields are private; treat the dataclass as opaque.
    """

    _cancelled: bool = field(default=False, init=False)
    _reason: Optional[str] = field(default=None, init=False)
    _cleanups: List[Tuple[str, Callable[[], None]]] = field(
        default_factory=list, init=False
    )
    _cleanups_ran: bool = field(default=False, init=False)
    _cleanup_errors: List[Tuple[str, str]] = field(
        default_factory=list, init=False
    )

    # --- producer side -------------------------------------------------

    def is_cancelled(self) -> bool:
        return self._cancelled

    def raise_if_cancelled(self) -> None:
        if self._cancelled:
            assert self._reason is not None
            raise Cancelled(self._reason)

    # --- consumer side -------------------------------------------------

    def cancel(self, reason: str) -> bool:
        """Signal cancellation. Returns True if this call was the trigger.

        Subsequent calls return False and do NOT overwrite the reason
        (set-once: first reason wins so audit logs are stable).
        """
        if self._cancelled:
            return False
        if not isinstance(reason, str) or not reason:
            raise ValueError("cancel reason must be a non-empty string")
        self._cancelled = True
        self._reason = reason
        return True

    @property
    def reason(self) -> Optional[str]:
        return self._reason

    # --- cleanup wiring ------------------------------------------------

    def register_cleanup(self, name: str, fn: Callable[[], None]) -> None:
        """Register a teardown callback.

        If the token is already cancelled when this is called, the
        cleanup runs *immediately* (and any error is captured into
        `cleanup_errors`). This avoids a late-registered handler
        silently leaking its resource.
        """
        if not isinstance(name, str) or not name:
            raise ValueError("cleanup name must be a non-empty string")
        if not callable(fn):
            raise TypeError("cleanup fn must be callable")

        if self._cancelled:
            self._run_one(name, fn)
            return
        self._cleanups.append((name, fn))

    def _run_one(self, name: str, fn: Callable[[], None]) -> None:
        try:
            fn()
        except BaseException as exc:  # noqa: BLE001 — capture all
            self._cleanup_errors.append((name, f"{type(exc).__name__}: {exc}"))

    def run_cleanups(self) -> None:
        """Run all pending cleanups in LIFO order. Idempotent.

        A cleanup that raises does NOT abort the rest; its exception is
        captured into `cleanup_errors` and the next cleanup still runs.
        """
        if self._cleanups_ran:
            return
        self._cleanups_ran = True
        # LIFO drain
        while self._cleanups:
            name, fn = self._cleanups.pop()
            self._run_one(name, fn)

    # --- introspection -------------------------------------------------

    @property
    def cleanups_ran(self) -> bool:
        return self._cleanups_ran

    @property
    def cleanup_errors(self) -> List[Tuple[str, str]]:
        # Return a copy so callers cannot mutate internal state.
        return list(self._cleanup_errors)

    def state(self) -> dict:
        """Sorted-key snapshot for logging / assertions."""
        return {
            "cancelled": self._cancelled,
            "cleanup_errors": list(self._cleanup_errors),
            "cleanups_pending": len(self._cleanups),
            "cleanups_ran": self._cleanups_ran,
            "reason": self._reason,
        }
