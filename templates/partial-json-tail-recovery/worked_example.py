"""Worked example: partial-json-tail-recovery.

Three scenarios that exercise the recovery engine end-to-end. All three are
realistic LLM-truncation shapes:

  1. Truncated mid-string-value: ``..."status": "in_pro``
  2. Truncated mid-key: ``..."severity": 3, "rea``
  3. Truncated inside a nested array of objects.
  4. (Bonus) Already-clean input takes the fast path.

Run with:

    python3 templates/partial-json-tail-recovery/worked_example.py
"""

from __future__ import annotations

import json
import os
import sys

# Allow running from repo root or from the template directory.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from recovery import recover  # noqa: E402


def _show(label: str, raw: str) -> None:
    print("=" * 72)
    print(label)
    print("-" * 72)
    print("input bytes:")
    print(raw)
    print("-" * 72)
    res = recover(raw)
    print(f"status            : {res.status}")
    print(f"confirmed_keys    : {res.confirmed_keys}")
    print(f"heuristic_keys    : {res.heuristic_keys}")
    print(f"dropped_tail      : {res.dropped_tail!r}")
    print("actions           :")
    for a in res.actions:
        print(f"  - {a}")
    print("parsed            :")
    print(json.dumps(res.parsed, indent=2, sort_keys=True))
    print()


def main() -> int:
    # 1. Truncated mid-string-value. The model committed `id`, `severity`,
    # `summary` cleanly, then started `status` and got cut. We expect:
    #   - confirmed: ["id", "severity", "summary"]
    #   - status key dropped entirely (never invent "in_progress")
    s1 = (
        '{"id": "INC-4421", "severity": 3, '
        '"summary": "queue fell behind during nightly batch", '
        '"status": "in_pro'
    )
    _show("scenario 1: mid-string-value truncation", s1)

    # 2. Truncated mid-key after a trailing comma. The model finished `severity`
    # cleanly, emitted a comma, started typing the next key as `"rea` and got
    # cut. We expect the trailing comma to be dropped and `rea*` discarded;
    # confirmed = ["id", "severity"].
    s2 = (
        '{"id": "INC-9001", "severity": 1, "rea'
    )
    _show("scenario 2: trailing-comma + half-typed key", s2)

    # 3. Nested array of objects, truncated inside the second element. The
    # outer object committed `incident_id` and opened `events`. The first event
    # closed cleanly; the second event committed `t` then got cut mid-`kind`.
    # We expect:
    #   - confirmed (outer): ["incident_id"]    # `events` is still open
    #   - heuristic (outer): ["events"]         # we closed it for them
    #   - the second event survives with just {"t": 1730000060}
    s3 = (
        '{"incident_id": "INC-77", "events": ['
        '{"t": 1730000000, "kind": "alert", "page": true}, '
        '{"t": 1730000060, "kind": "ack'
    )
    _show("scenario 3: nested array, truncated inside element", s3)

    # 4. Already-valid input -> fast path, status=clean.
    s4 = '{"a": 1, "b": [1, 2, 3], "c": {"nested": true}}'
    _show("scenario 4: already-valid input", s4)

    # ---- Invariants we assert in-process so a regression fails the run ----
    r1 = recover(s1)
    assert r1.status == "recovered", r1
    assert r1.confirmed_keys == ["id", "severity", "summary"], r1.confirmed_keys
    assert "status" not in (r1.parsed or {}), r1.parsed

    r2 = recover(s2)
    assert r2.status == "recovered", r2
    assert r2.confirmed_keys == ["id", "severity"], r2.confirmed_keys
    assert list((r2.parsed or {}).keys()) == ["id", "severity"], r2.parsed

    r3 = recover(s3)
    assert r3.status == "recovered", r3
    assert r3.confirmed_keys == ["incident_id"], r3.confirmed_keys
    assert "events" in r3.heuristic_keys, r3.heuristic_keys
    events = (r3.parsed or {}).get("events")
    assert isinstance(events, list) and len(events) == 2, events
    assert events[0] == {"t": 1730000000, "kind": "alert", "page": True}
    assert events[1] == {"t": 1730000060}, events[1]

    r4 = recover(s4)
    assert r4.status == "clean", r4
    assert r4.heuristic_keys == [], r4
    assert r4.confirmed_keys == ["a", "b", "c"], r4.confirmed_keys

    print("all invariants OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
