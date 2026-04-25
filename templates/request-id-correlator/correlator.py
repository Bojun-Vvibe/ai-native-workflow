"""
request-id-correlator — in-process correlation-id propagation primitive.

The wire format (W3C-traceparent, B3, x-request-id, etc.) is the caller's
job. This module owns the *in-process* part — once a correlation id has
been minted at the entry point of a request, every log line emitted by
any nested helper function, await point, or thread should carry it
automatically, with zero plumbing through function signatures.

The substrate is `contextvars.ContextVar`, which is the Python primitive
that survives `await` boundaries (PEP 567) and is inherited by
`asyncio.create_task()`. This template wraps it with the four properties
ad-hoc usage gets wrong:

  1. Auto-injection into stdlib logging via a `logging.Filter` so every
     `logger.info("...")` call within the active context gets the id
     stamped on the LogRecord without changing the call site.
  2. Detection of orphan log lines (records emitted with no active
     correlation context). In production this almost always means
     accidental background work outside the request lifecycle —
     surfaced as `record.correlation_id == "<orphan>"` so log queries
     can find them instead of silently filtering them out.
  3. Safe `asyncio.create_task` wrapper that preserves the context. The
     plain `create_task` *does* inherit the current context (good), but
     a long-lived background task started outside any request inherits
     `<orphan>` forever — `spawn_task` makes that explicit.
  4. Thread propagation via a `submit_with_context` helper for
     `concurrent.futures.Executor` — bare `executor.submit(fn)` does
     NOT inherit contextvars across the thread boundary, which is the
     single most common cause of "the id is right at the entry point
     and missing in the worker thread."

Public API:
    enter_request(request_id=None) -> Token        # bind id; returns reset token
    leave_request(token) -> None                   # restore previous id
    request_scope(request_id=None) -> ctx manager  # bind+restore in one block
    current_id() -> str | None                     # the active id, or None
    install_logging_filter(logger=None) -> Filter  # auto-stamp LogRecords
    spawn_task(coro, *, name=None) -> asyncio.Task # create_task that asserts a context
    submit_with_context(executor, fn, *args, **kw) # cross-thread propagation

The orphan sentinel is `"<orphan>"` (not `None`) because log queries on
"`correlation_id is null`" silently miss records where the field was never
set vs. records where it was explicitly set to absent.
"""

from __future__ import annotations

import asyncio
import contextlib
import contextvars
import logging
import secrets
from concurrent.futures import Executor, Future
from typing import Any, Callable, Coroutine, Iterator, Optional, TypeVar

ORPHAN_SENTINEL = "<orphan>"

# Module-level ContextVar — one per process. Default None means "no active
# request"; the logging filter substitutes ORPHAN_SENTINEL when stamping.
_current_request_id: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "request_id", default=None
)


def _mint_id() -> str:
    """Default id generator. 16 hex chars from a CSPRNG.

    Caller may pass their own at `enter_request(request_id=…)` if they
    want to honor an upstream `X-Request-Id` header.
    """
    return secrets.token_hex(8)


def enter_request(request_id: Optional[str] = None) -> contextvars.Token:
    """Bind a correlation id to the current context. Returns the reset token
    to be passed to `leave_request`.

    If `request_id` is None, a fresh 16-hex id is minted.
    """
    if request_id is None:
        request_id = _mint_id()
    if not isinstance(request_id, str) or not request_id:
        raise ValueError(
            f"request_id must be a non-empty str, got {request_id!r}"
        )
    return _current_request_id.set(request_id)


def leave_request(token: contextvars.Token) -> None:
    """Restore the previous correlation id (or None at the outermost frame)."""
    _current_request_id.reset(token)


@contextlib.contextmanager
def request_scope(request_id: Optional[str] = None) -> Iterator[str]:
    """Bind a correlation id for the body of a `with` block, yielding the
    bound id so the caller can echo it back to the client (e.g. as a
    response header).
    """
    token = enter_request(request_id)
    try:
        yield _current_request_id.get()  # type: ignore[misc]
    finally:
        leave_request(token)


def current_id() -> Optional[str]:
    """Return the active correlation id, or None if no request is in scope."""
    return _current_request_id.get()


class CorrelationFilter(logging.Filter):
    """Logging filter that stamps `record.correlation_id` on every LogRecord.

    Records emitted outside any `request_scope` get `ORPHAN_SENTINEL` so log
    queries can find them. The filter never rejects records (always returns
    True) — it's a stamper, not a gate.
    """

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003
        rid = _current_request_id.get()
        record.correlation_id = rid if rid is not None else ORPHAN_SENTINEL
        return True


def install_logging_filter(
    target: Optional[logging.Filterer] = None,
) -> CorrelationFilter:
    """Attach a `CorrelationFilter` to `target` (root logger by default).

    `target` may be a `logging.Logger` OR a `logging.Handler` — both inherit
    from `logging.Filterer` and expose `addFilter` / `.filters`. Attaching
    to a HANDLER is usually correct: filters on a logger only fire for
    records emitted on that logger directly (not for records propagated up
    from child loggers), while filters on a handler fire for every record
    the handler sees.

    Returns the installed filter so the caller can later remove it. Idempotent
    on the same target — if a `CorrelationFilter` is already attached, returns
    the existing one rather than stacking duplicates.
    """
    if target is None:
        target = logging.getLogger()
    for f in target.filters:
        if isinstance(f, CorrelationFilter):
            return f
    flt = CorrelationFilter()
    target.addFilter(flt)
    return flt


T = TypeVar("T")


def spawn_task(
    coro: Coroutine[Any, Any, T],
    *,
    name: Optional[str] = None,
    require_context: bool = True,
) -> asyncio.Task[T]:
    """Create an asyncio task that explicitly asserts a correlation context.

    `asyncio.create_task` *does* inherit the current ContextVar values, but
    silently — a task spawned outside any `request_scope` will run with
    `current_id() == None` and emit orphan log lines forever. Set
    `require_context=False` to opt out (e.g. for legitimate cron-like
    background tasks); the default loud failure catches the common bug.
    """
    if require_context and _current_request_id.get() is None:
        raise RuntimeError(
            "spawn_task() called outside an active request_scope; "
            "the resulting task would emit orphan log lines. "
            "Wrap the call site in `with request_scope():` or pass "
            "`require_context=False` to opt out explicitly."
        )
    return asyncio.create_task(coro, name=name)


def submit_with_context(
    executor: Executor,
    fn: Callable[..., T],
    *args: Any,
    **kwargs: Any,
) -> Future:
    """Submit `fn` to `executor` with the current ContextVar values copied
    into the worker thread.

    Plain `executor.submit(fn)` does NOT propagate ContextVars across the
    thread boundary — the worker runs with whatever the thread had at
    creation time (usually nothing), so `current_id()` returns None inside
    the worker. This wrapper snapshots the caller's context and runs `fn`
    inside it so logging stamps the right id.
    """
    ctx = contextvars.copy_context()
    return executor.submit(ctx.run, fn, *args, **kwargs)
