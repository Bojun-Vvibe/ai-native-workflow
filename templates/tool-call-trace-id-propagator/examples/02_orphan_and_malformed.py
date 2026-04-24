"""Worked example 2 — orphan span detection + malformed header rejection.

Demonstrates the two failure modes the validator catches:
  1. A span whose ``parent_span_id`` is not present in the trace (orphan):
     happens when an intermediate hop drops its span record (crash, log
     rotation race, OOM kill before flush).
  2. A wire header that's been truncated / mutated in transit gets rejected
     at parse time, so the bad span never enters the recorder.
"""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from trace import (
    Recorder,
    TraceError,
    child,
    new_root,
    parse,
    validate_records,
)


def main() -> None:
    rng = random.Random(7)
    rec = Recorder()

    # ------------------------------------------------------------------
    # Build a 3-level chain root -> mid -> leaf, but pretend "mid" never
    # got recorded (its process crashed before flushing).
    # ------------------------------------------------------------------
    root = new_root(rng)
    mid = child(root, rng)
    leaf = child(mid, rng)

    s_root = rec.open(root, "mission.run", started_ms=0)
    s_root.finish("ok", ended_ms=100)
    # NOTE: mid is intentionally NOT opened on the recorder.
    s_leaf = rec.open(leaf, "tool.write_file", started_ms=40)
    s_leaf.finish("error", ended_ms=55, error_class="host_io")

    report = validate_records(rec.records())
    print("validation with one orphan:")
    print(json.dumps(report, indent=2, sort_keys=True))
    assert not report["ok"]
    codes = sorted({e["code"] for e in report["errors"]})
    assert codes == ["orphan_span"], f"expected only orphan_span, got {codes}"

    # ------------------------------------------------------------------
    # Malformed wire headers must raise at parse time.
    # ------------------------------------------------------------------
    samples = [
        "v=1;trace=abc;span=def;parent=000;flags=01",  # short hex
        "v=2;trace=" + "a" * 32 + ";span=" + "b" * 16 + ";parent=" + "0" * 16 + ";flags=01",  # wrong version
        "v=1;trace=" + "a" * 32 + ";span=" + "0" * 16 + ";parent=" + "0" * 16 + ";flags=01",  # zero span
        "v=1;trace=" + "a" * 32 + ";span=" + "c" * 16 + ";parent=" + "c" * 16 + ";flags=01",  # span==parent
    ]
    print("\nrejecting malformed headers:")
    for raw in samples:
        try:
            parse(raw)
            print(f"  ACCEPTED (BUG): {raw}")
        except TraceError as e:
            print(f"  rejected: {e}")


if __name__ == "__main__":
    main()
