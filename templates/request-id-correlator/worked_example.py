"""
Worked example for request-id-correlator.

Five scenarios, all run in one process:

  1. Basic — `request_scope` binds an id and a nested helper logs it.
  2. Orphan — a log line emitted outside any scope gets `<orphan>`.
  3. Async — `spawn_task` propagates the id into the new task; outside-scope
     spawn raises loudly.
  4. Thread — `submit_with_context` propagates the id across a thread
     boundary; bare `executor.submit` does NOT (we prove both).
  5. Custom id — caller supplies an upstream `X-Request-Id`-style id and the
     correlator honors it instead of minting.

Output is captured by a custom in-memory log handler so the assertions are
deterministic.
"""

from __future__ import annotations

import asyncio
import logging
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import List

sys.path.insert(0, str(Path(__file__).parent))

from correlator import (  # noqa: E402
    ORPHAN_SENTINEL,
    current_id,
    install_logging_filter,
    request_scope,
    spawn_task,
    submit_with_context,
)


class CapturingHandler(logging.Handler):
    """Record every emitted (correlation_id, message) pair in memory."""

    def __init__(self) -> None:
        super().__init__()
        self.records: List[tuple[str, str]] = []

    def emit(self, record: logging.LogRecord) -> None:
        rid = getattr(record, "correlation_id", "<no-filter>")
        self.records.append((rid, record.getMessage()))


def setup_logging() -> CapturingHandler:
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(logging.DEBUG)
    handler = CapturingHandler()
    # Attach filter to the HANDLER, not a logger — filters on a logger only
    # run for records emitted on that logger directly, not for records
    # propagated up from child loggers. Filters on a handler run for every
    # record the handler sees.
    install_logging_filter(handler)
    root.addHandler(handler)
    return handler


log = logging.getLogger("worked_example")


def banner(title: str) -> None:
    print()
    print("=" * 64)
    print(title)
    print("=" * 64)


def scenario_basic(handler: CapturingHandler) -> None:
    banner("Scenario 1: basic — request_scope binds id, nested helper logs it")
    handler.records.clear()
    with request_scope() as rid:
        log.info("entered request")
        helper_function()
    print(f"  bound id: {rid}")
    for cid, msg in handler.records:
        print(f"  [{cid}] {msg}")
    assert all(cid == rid for cid, _ in handler.records), handler.records


def helper_function() -> None:
    """Three call frames deep — proves we don't have to thread the id through."""
    log.info(f"helper sees id={current_id()}")


def scenario_orphan(handler: CapturingHandler) -> None:
    banner("Scenario 2: orphan — log line outside any scope gets '<orphan>'")
    handler.records.clear()
    log.info("emitted before any request_scope")
    cid, msg = handler.records[0]
    print(f"  [{cid}] {msg}")
    assert cid == ORPHAN_SENTINEL, cid


async def _async_worker() -> str:
    log.info(f"async worker sees id={current_id()}")
    return current_id() or "<none>"


async def _async_main(handler: CapturingHandler) -> None:
    handler.records.clear()
    with request_scope("upstream-abc-123") as rid:
        log.info("about to spawn task")
        task = spawn_task(_async_worker())
        worker_saw = await task
    print(f"  outer scope bound id: {rid}")
    print(f"  worker saw id:       {worker_saw}")
    for cid, msg in handler.records:
        print(f"  [{cid}] {msg}")
    assert worker_saw == rid

    # Now prove the loud-failure path.
    leaked_coro = _async_worker()
    try:
        spawn_task(leaked_coro)
    except RuntimeError as e:
        leaked_coro.close()  # avoid "coroutine was never awaited" warning
        print(f"  spawn_task outside scope correctly raised: {type(e).__name__}")
    else:
        raise AssertionError("spawn_task outside scope should have raised")


def scenario_async(handler: CapturingHandler) -> None:
    banner("Scenario 3: async — spawn_task propagates id, outside-scope raises")
    asyncio.run(_async_main(handler))


def _thread_worker(label: str) -> tuple[str, str]:
    seen = current_id() or "<none>"
    log.info(f"{label} thread sees id={seen}")
    return label, seen


def scenario_thread(handler: CapturingHandler) -> None:
    banner("Scenario 4: thread — submit_with_context vs bare submit")
    handler.records.clear()
    with ThreadPoolExecutor(max_workers=2) as ex:
        with request_scope("req-thread-xyz") as rid:
            print(f"  bound id: {rid}")
            f_good = submit_with_context(ex, _thread_worker, "with_context")
            f_bad = ex.submit(_thread_worker, "bare_submit")
            good_label, good_seen = f_good.result()
            bad_label, bad_seen = f_bad.result()
    print(f"  {good_label}: {good_seen}")
    print(f"  {bad_label}: {bad_seen}")
    for cid, msg in handler.records:
        print(f"  [{cid}] {msg}")
    assert good_seen == rid, good_seen
    assert bad_seen == "<none>", bad_seen


def scenario_custom_id(handler: CapturingHandler) -> None:
    banner("Scenario 5: custom id — honor upstream X-Request-Id")
    handler.records.clear()
    with request_scope("inbound-header-deadbeef0001") as rid:
        log.info("processing")
    cid, _ = handler.records[0]
    print(f"  bound id: {rid}")
    print(f"  log line stamped with: {cid}")
    assert cid == "inbound-header-deadbeef0001", cid


if __name__ == "__main__":
    handler = setup_logging()
    scenario_basic(handler)
    scenario_orphan(handler)
    scenario_async(handler)
    scenario_thread(handler)
    scenario_custom_id(handler)
    print()
    print("All scenarios passed.")
