"""End-to-end smoke test for cross-tick-state-handoff.

Simulates four successive dispatcher ticks. Each tick:
  1. loads the committed envelope from the previous tick
  2. picks the next pending mission
  3. records the outcome
  4. commits

Then we simulate a *crash* mid-tick (transaction body raises) and
prove the envelope is unchanged. Finally we attempt to load with a
mismatched schema_version and prove HandoffError fires.
"""

from __future__ import annotations

import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from handoff import HandoffError, HandoffStore  # noqa: E402


def tick(store: HandoffStore, tick_id: int, mission: str, outcome: str) -> None:
    with store.transaction() as state:
        state.setdefault("tick_count", 0)
        state.setdefault("history", [])
        state["tick_count"] += 1
        state["history"].append(
            {"tick": tick_id, "mission": mission, "outcome": outcome}
        )
        state["last_tick"] = tick_id


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "state", "handoff.json")
        store = HandoffStore(path, schema_version=1)

        # First load: nothing yet
        assert store.load() is None
        print("tick 0: no prior envelope (clean start)")

        # Four successive ticks
        for i, (mission, outcome) in enumerate(
            [
                ("templates", "shipped 2"),
                ("missions", "shipped 1"),
                ("oss", "skipped: nothing actionable"),
                ("templates", "shipped 1"),
            ],
            start=1,
        ):
            tick(store, i, mission, outcome)
            snap = store.snapshot()
            assert snap is not None
            print(
                f"tick {i}: count={snap['tick_count']} "
                f"last={snap['last_tick']} mission={mission!r}"
            )

        # Verify final state
        final = store.snapshot()
        assert final is not None
        assert final["tick_count"] == 4
        assert len(final["history"]) == 4
        print(f"final history has {len(final['history'])} entries")

        # Crash safety: raise inside transaction, envelope must be unchanged
        before = store.snapshot()
        try:
            with store.transaction() as state:
                state["tick_count"] = 999
                state["history"].clear()
                raise RuntimeError("simulated mid-tick crash")
        except RuntimeError as e:
            print(f"caught simulated crash: {e}")
        after = store.snapshot()
        assert before == after, "envelope mutated despite exception"
        print("crash-safety: envelope unchanged after exception (OK)")

        # Schema-version guard
        wrong = HandoffStore(path, schema_version=2)
        try:
            wrong.load()
        except HandoffError as e:
            print(f"schema guard fired: {e}")
        else:
            raise AssertionError("expected HandoffError on version mismatch")

    print("ALL CHECKS PASSED")


if __name__ == "__main__":
    main()
