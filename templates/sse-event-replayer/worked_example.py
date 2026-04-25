"""Worked example for sse-event-replayer.

Drives four scenarios end-to-end:
  1. Cold consumer (no Last-Event-ID) — DELIVER everything.
  2. Reconnect mid-stream with a current cursor — DELIVER tail.
  3. Reconnect with a cursor too far behind retention — TOO_OLD.
  4. Reconnect with a cursor *ahead* of our latest — FUTURE_CURSOR
     (replica desync).
Plus producer-side guardrails:
  5. Same-id-same-payload re-append is silently absorbed.
  6. Same-id-different-payload re-append raises IdPayloadConflict.
  7. Out-of-order append raises NonMonotonicId.
"""

from __future__ import annotations

import json

from replayer import (
    Event,
    EventReplayer,
    IdPayloadConflict,
    NonMonotonicId,
)


def _row(label: str, result) -> None:
    print(f"  {label:<28} verdict={result.verdict:<14} "
          f"events={[e.id for e in result.events]} "
          f"oldest_retained_id={result.oldest_retained_id} "
          f"latest_id={result.latest_id}")


def main() -> None:
    print("=== sse-event-replayer worked example ===\n")

    # --- Scenario 1: cold consumer ------------------------------------
    print("[1] cold consumer (last_event_id=None) -> DELIVER all")
    r = EventReplayer(max_retained=8)
    for i in range(1, 6):
        r.append(Event(id=i, event="token", payload={"text": f"chunk-{i}"}))
    res = r.since(None)
    _row("since(None)", res)
    assert res.verdict == "DELIVER" and len(res.events) == 5
    assert [e.id for e in res.events] == [1, 2, 3, 4, 5]
    print()

    # --- Scenario 2: reconnect mid-stream -----------------------------
    print("[2] reconnect with last_event_id=3 -> DELIVER tail [4,5]")
    res = r.since(3)
    _row("since(3)", res)
    assert res.verdict == "DELIVER"
    assert [e.id for e in res.events] == [4, 5]

    print("    (cursor caught up; another since(5) -> EMPTY)")
    res = r.since(5)
    _row("since(5)", res)
    assert res.verdict == "EMPTY"
    print()

    # --- Scenario 3: TOO_OLD after eviction ---------------------------
    print("[3] retention rolls past consumer's cursor -> TOO_OLD")
    r2 = EventReplayer(max_retained=4)
    for i in range(1, 11):
        r2.append(Event(id=i, event="token", payload={"text": f"t-{i}"}))
    snap = r2.snapshot()
    print(f"    snapshot: retained={snap['retained']} "
          f"oldest_id={snap['oldest_id']} latest_id={snap['latest_id']} "
          f"evicted={snap['stats']['evicted']}")
    res = r2.since(2)  # cursor at 2, but we only hold 7..10
    _row("since(2)", res)
    assert res.verdict == "TOO_OLD"
    assert res.oldest_retained_id == 7

    # Boundary: a cursor at oldest-1 == 6 is still serviceable.
    res = r2.since(6)
    _row("since(6) [boundary]", res)
    assert res.verdict == "DELIVER"
    assert [e.id for e in res.events] == [7, 8, 9, 10]
    print()

    # --- Scenario 4: FUTURE_CURSOR (replica desync) -------------------
    print("[4] consumer cursor ahead of our latest -> FUTURE_CURSOR")
    res = r.since(99)  # r's latest is 5
    _row("since(99)", res)
    assert res.verdict == "FUTURE_CURSOR"
    assert res.latest_id == 5
    print()

    # --- Scenario 5: idempotent re-append -----------------------------
    print("[5] same-id-same-payload re-append is silently absorbed")
    r3 = EventReplayer(max_retained=8)
    e = Event(id=1, event="token", payload={"text": "hi"})
    r3.append(e)
    r3.append(e)  # idempotent
    snap = r3.snapshot()
    print(f"    appended={snap['stats']['appended']} "
          f"duplicate_absorbed={snap['stats']['duplicate_absorbed']} "
          f"retained={snap['retained']}")
    assert snap["stats"]["appended"] == 1
    assert snap["stats"]["duplicate_absorbed"] == 1
    print()

    # --- Scenario 6: producer payload conflict ------------------------
    print("[6] same-id-different-payload -> IdPayloadConflict")
    raised = None
    try:
        r3.append(Event(id=1, event="token", payload={"text": "DIFFERENT"}))
    except IdPayloadConflict as ex:
        raised = str(ex)
    print(f"    raised: {raised}")
    assert raised is not None and "id=1" in raised
    print()

    # --- Scenario 7: non-monotonic append -----------------------------
    print("[7] non-monotonic append -> NonMonotonicId")
    r3.append(Event(id=2, event="token", payload={"text": "ok"}))
    r3.append(Event(id=5, event="token", payload={"text": "ok"}))
    raised = None
    try:
        r3.append(Event(id=4, event="token", payload={"text": "late"}))
    except NonMonotonicId as ex:
        raised = str(ex)
    print(f"    raised: {raised}")
    assert raised is not None and "id=4" in raised
    print()

    # --- Final stats --------------------------------------------------
    print("[final stats] r.snapshot() =")
    print(json.dumps(r.snapshot(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
