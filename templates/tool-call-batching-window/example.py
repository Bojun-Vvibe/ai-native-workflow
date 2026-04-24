#!/usr/bin/env python3
"""End-to-end worked example for tool-call-batching-window.

Three scenarios:

  1. Size-cap trip: submit 7 items with max_batch_size=3 → two batches
     auto-flush on submit, one deadline-flush picks up the trailing 1.
  2. Deadline trip: submit 2 items, no further activity, tick past the
     window → both flushed in one batch.
  3. bulk_fn raises: every pending handle in that flush gets the same
     exception. Asserts that submit-order is preserved.

The "remote tool" we batch is a synthetic `bulk_read_files`: a single
call that pretends to read N paths and returns N stat dicts. We count
how many times it is called to *prove* batching reduced fanout.

Run:
    python3 example.py
"""

from __future__ import annotations

import json
from typing import Any, List

from window import BatchingWindow, BatchSizeMismatch, WindowClosed


# ----- the "tool" we are batching ---------------------------------------

call_log: List[List[str]] = []


def bulk_read_files(paths: List[str]) -> List[dict]:
    """Pretend remote bulk read. Records the per-call batch size."""
    call_log.append(list(paths))
    return [{"path": p, "size_b": 100 + i} for i, p in enumerate(paths)]


def bulk_read_files_flaky(paths: List[str]) -> List[dict]:
    raise ConnectionError(f"upstream 503 for batch of {len(paths)}")


# ----- scenario 1: size-cap trips with a trailing deadline flush --------

def scenario_one_size_cap() -> dict:
    print("=== scenario 1: size-cap trips, then deadline picks up trailer ===")
    call_log.clear()
    win = BatchingWindow(
        bulk_fn=bulk_read_files,
        max_wait_s=0.050,      # 50ms window
        max_batch_size=3,
    )

    handles = []
    t = 1000.0

    # Submit 7 items at t=1000.000, 1000.001, ... 1000.006
    for i in range(7):
        h = win.submit(f"/data/{i}.txt", now_s=t + i * 0.001)
        handles.append(h)

    # After submitting 7 with size=3 cap, two flushes have already
    # fired automatically (after items 3 and 6). One item remains.
    print("after-submits state:", json.dumps(win.state(), sort_keys=True))

    # Advance past the 50ms window from the trailing item's first_submit.
    win.tick(now_s=t + 0.006 + 0.060)

    print("after-tick state:", json.dumps(win.state(), sort_keys=True))
    print("bulk_fn call_log sizes:", [len(b) for b in call_log])
    print("first batch contents:", call_log[0])

    results = [h.result() for h in handles]
    print("first 3 results:", results[:3])
    print()
    return {
        "call_log_sizes": [len(b) for b in call_log],
        "all_resolved": all(h.resolved for h in handles),
        "results_len": len(results),
        "state": win.state(),
    }


# ----- scenario 2: pure deadline trip -----------------------------------

def scenario_two_deadline() -> dict:
    print("=== scenario 2: deadline-only trip ===")
    call_log.clear()
    win = BatchingWindow(
        bulk_fn=bulk_read_files,
        max_wait_s=0.025,
        max_batch_size=10,
    )
    h1 = win.submit("/etc/hosts", now_s=2000.000)
    h2 = win.submit("/etc/passwd", now_s=2000.005)

    # Tick at 2000.020 — under the 25ms window, no flush.
    flushed_early = win.tick(now_s=2000.020)
    print("tick at +20ms flushed:", flushed_early)

    # Tick at 2000.030 — past the deadline.
    flushed_late = win.tick(now_s=2000.030)
    print("tick at +30ms flushed:", flushed_late)
    print("bulk_fn call_log:", call_log)
    print("h1.result():", h1.result())
    print("h2.result():", h2.result())
    print()
    return {
        "flushed_early": flushed_early,
        "flushed_late": flushed_late,
        "call_count": len(call_log),
        "h1": h1.result(),
        "h2": h2.result(),
    }


# ----- scenario 3: bulk_fn raises; every handle inherits the error ------

def scenario_three_bulk_raises() -> dict:
    print("=== scenario 3: bulk_fn raises -> every handle inherits ===")
    call_log.clear()
    win = BatchingWindow(
        bulk_fn=bulk_read_files_flaky,
        max_wait_s=0.010,
        max_batch_size=5,
    )
    h_a = win.submit("/a", now_s=3000.0)
    h_b = win.submit("/b", now_s=3000.001)
    h_c = win.submit("/c", now_s=3000.002)

    # Force flush.
    n = win.flush(now_s=3000.003)
    print("manual flush drained:", n)

    errors = []
    for label, h in [("a", h_a), ("b", h_b), ("c", h_c)]:
        try:
            h.result()
        except ConnectionError as exc:
            errors.append((label, str(exc)))

    print("errors:", errors)
    print("state:", json.dumps(win.state(), sort_keys=True))
    print()
    return {"errors": errors, "state": win.state()}


# ----- scenario 4: close() refuses further submits ----------------------

def scenario_four_close() -> dict:
    print("=== scenario 4: close() drains, then rejects further submits ===")
    call_log.clear()
    win = BatchingWindow(
        bulk_fn=bulk_read_files,
        max_wait_s=10.0,
        max_batch_size=10,
    )
    h = win.submit("/late.txt", now_s=4000.0)
    win.close(now_s=4000.001)
    rejected = False
    try:
        win.submit("/too-late.txt", now_s=4000.002)
    except WindowClosed:
        rejected = True
    print("h.result():", h.result())
    print("submit-after-close rejected:", rejected)
    print("state:", json.dumps(win.state(), sort_keys=True))
    print()
    return {"rejected": rejected, "h": h.result(), "state": win.state()}


def main() -> int:
    s1 = scenario_one_size_cap()
    s2 = scenario_two_deadline()
    s3 = scenario_three_bulk_raises()
    s4 = scenario_four_close()

    # Assertions
    # 7 items, batch=3 → flushes of size [3, 3, 1]
    assert s1["call_log_sizes"] == [3, 3, 1], s1
    assert s1["all_resolved"] is True
    assert s1["results_len"] == 7
    assert s1["state"]["pending_count"] == 0
    assert s1["state"]["size_trips"] == 2
    assert s1["state"]["deadline_trips"] == 1
    assert s1["state"]["flushes_total"] == 3

    # Deadline scenario: early tick = 0 flushed, late tick = 2 flushed
    assert s2["flushed_early"] == 0, s2
    assert s2["flushed_late"] == 2, s2
    assert s2["call_count"] == 1
    assert s2["h1"]["path"] == "/etc/hosts"
    assert s2["h2"]["path"] == "/etc/passwd"

    # Error fanout preserves submit-order
    assert [lbl for lbl, _ in s3["errors"]] == ["a", "b", "c"], s3
    assert all("503" in msg for _, msg in s3["errors"])
    assert s3["state"]["manual_flushes"] == 1

    # Close scenario
    assert s4["rejected"] is True
    assert s4["h"]["path"] == "/late.txt"
    assert s4["state"]["closed"] is True

    print("=== all assertions passed ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
