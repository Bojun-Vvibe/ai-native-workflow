#!/usr/bin/env python3
"""End-to-end worked example for streaming-cancellation-token.

Two scenarios, both run for real:

  1. A streaming "model call" produces 10 chunks, each gated on the
     token. The consumer cancels after chunk 4. The producer observes
     on the next check, runs its registered cleanups (LIFO), and
     raises `Cancelled`.

  2. A cleanup callback raises mid-teardown. The remaining cleanups
     still run, and the error surfaces in `cleanup_errors`.

Run:
    python3 example.py
"""

from __future__ import annotations

import json
from typing import List

from cancel import CancellationToken, Cancelled


def fake_streaming_producer(token: CancellationToken, n_chunks: int) -> List[str]:
    """Emit `n_chunks` synthetic chunks, polling the token between each.

    Caller-side cleanups simulate: a temp file we opened, a UI element
    we showed, a debit row we wrote. Registered in dependency order;
    they will tear down LIFO.
    """
    emitted: List[str] = []

    open_calls: List[str] = []
    flush_calls: List[str] = []
    debit_calls: List[str] = []

    # Register in dependency order: open -> flush -> debit
    token.register_cleanup("close_temp_file",
                           lambda: open_calls.append("closed"))
    token.register_cleanup("flush_ui_buffer",
                           lambda: flush_calls.append("flushed"))
    token.register_cleanup("rollback_debit",
                           lambda: debit_calls.append("rolled_back"))

    try:
        for i in range(n_chunks):
            token.raise_if_cancelled()
            emitted.append(f"chunk-{i}")
    finally:
        token.run_cleanups()

    return emitted


def scenario_one_clean_cancel() -> dict:
    print("=== scenario 1: clean mid-stream cancel ===")
    token = CancellationToken()
    emitted: List[str] = []
    err_reason = None

    # Drive the producer step-by-step so we can interject cancel().
    # In real code the consumer might be a different thread / coroutine;
    # here we simulate by stopping after chunk 4 and re-entering.
    try:
        for i in range(10):
            token.raise_if_cancelled()
            emitted.append(f"chunk-{i}")
            if i == 3:
                # Consumer decides: stop. Reason recorded set-once.
                first = token.cancel("user_pressed_escape")
                second = token.cancel("ui_closed_window")  # ignored
                print(json.dumps({
                    "consumer_event": "cancel",
                    "first_call_was_trigger": first,
                    "second_call_was_trigger": second,
                    "reason_after_two_calls": token.reason,
                }, sort_keys=True))
    except Cancelled as exc:
        err_reason = exc.reason
    finally:
        token.run_cleanups()
        # Idempotent: a second drain is a no-op.
        token.run_cleanups()

    state = token.state()
    print("emitted:", emitted)
    print("raised_reason:", err_reason)
    print("token_state:", json.dumps(state, sort_keys=True))
    print()
    return {
        "emitted_count": len(emitted),
        "raised_reason": err_reason,
        "state": state,
    }


def scenario_two_cleanup_raises() -> dict:
    print("=== scenario 2: a cleanup raises; the others still run ===")
    token = CancellationToken()

    log: List[str] = []

    def good_first():
        log.append("good_first ran")

    def bad_middle():
        log.append("bad_middle entered")
        raise RuntimeError("disk full")

    def good_last():
        log.append("good_last ran")

    # Registered in order: good_first, bad_middle, good_last.
    # LIFO teardown: good_last, bad_middle (raises), good_first.
    # Order of `log` proves bad_middle did NOT short-circuit good_first.
    token.register_cleanup("good_first", good_first)
    token.register_cleanup("bad_middle", bad_middle)
    token.register_cleanup("good_last", good_last)

    token.cancel("eval_loop_budget_exhausted")
    token.run_cleanups()

    state = token.state()
    print("cleanup_log:", log)
    print("cleanup_errors:", state["cleanup_errors"])
    print("token_state:", json.dumps(state, sort_keys=True))
    print()
    return {"log": log, "state": state}


def scenario_three_late_register() -> dict:
    print("=== scenario 3: register_cleanup AFTER cancel runs immediately ===")
    token = CancellationToken()
    token.cancel("upstream_quota_exceeded")

    fired: List[str] = []
    token.register_cleanup("late_handler",
                           lambda: fired.append("late_handler ran"))

    state = token.state()
    print("fired:", fired)
    print("token_state:", json.dumps(state, sort_keys=True))
    print()
    return {"fired": fired, "state": state}


def main() -> int:
    s1 = scenario_one_clean_cancel()
    s2 = scenario_two_cleanup_raises()
    s3 = scenario_three_late_register()

    # Assertions — fail loudly if behaviour drifts.
    assert s1["emitted_count"] == 4, s1
    assert s1["raised_reason"] == "user_pressed_escape", s1
    assert s1["state"]["cancelled"] is True
    assert s1["state"]["cleanups_ran"] is True
    assert s1["state"]["cleanups_pending"] == 0
    assert s1["state"]["cleanup_errors"] == []

    assert s2["log"] == [
        "good_last ran",
        "bad_middle entered",
        "good_first ran",
    ], s2
    assert len(s2["state"]["cleanup_errors"]) == 1
    assert s2["state"]["cleanup_errors"][0][0] == "bad_middle"
    assert "RuntimeError" in s2["state"]["cleanup_errors"][0][1]

    assert s3["fired"] == ["late_handler ran"], s3
    assert s3["state"]["cleanups_pending"] == 0

    print("=== all assertions passed ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
