"""Worked example 2 — refund re-arms warn rungs; double-refund is idempotent.

Sequence:
  1. Spend up to 0.92 (crosses 60% and 85% rungs once each).
  2. A tool-call rollback refunds the 0.30 spend that crossed 85%.
     - Running total drops to 0.62.
     - The 0.85 rung gets re-armed (we are now below it).
     - The 0.60 rung stays armed (we are still above it).
  3. A new spend pushes us back above 0.85: the 0.85 rung re-warns.
     This proves the refund-then-respend pattern doesn't silently mask the
     second crossing.
  4. Refunding the same call_id again returns ``status="already_refunded"``.
  5. Refunding an unknown id returns ``status="unknown"``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fence import Ledger, Spend


def main() -> None:
    led = Ledger(budget_usd=1.00)

    print("step 1 — spend up to 0.92:")
    for cid, amt in [("a", 0.40), ("b", 0.22), ("c", 0.30)]:
        v = led.charge(Spend(cid, amt))
        print(f"  charge {cid} ${amt:.2f} ->", json.dumps(v.to_dict(), sort_keys=True))
    assert abs(led.spent_usd - 0.92) < 1e-9
    assert led.warned_rungs == {0.60, 0.85}

    print("\nstep 2 — refund call 'c' (the one that crossed 85%):")
    r = led.refund("c")
    print(" ", json.dumps(r, sort_keys=True))
    assert r["status"] == "refunded"
    assert led.warned_rungs == {0.60}, led.warned_rungs
    assert 0.85 in r["rearmed_rungs"]

    print("\nstep 3 — new spend climbs back above 0.85:")
    v = led.charge(Spend("d", 0.25))  # 0.62 -> 0.87
    print(" ", json.dumps(v.to_dict(), sort_keys=True))
    assert v.status == "warn" and v.rung == 0.85, "85% must re-warn after refund"

    print("\nstep 4 — double-refund same call_id is idempotent:")
    r2 = led.refund("c")
    print(" ", json.dumps(r2, sort_keys=True))
    assert r2["status"] == "already_refunded"

    print("\nstep 5 — refunding an unknown call_id:")
    r3 = led.refund("does-not-exist")
    print(" ", json.dumps(r3, sort_keys=True))
    assert r3["status"] == "unknown"

    print("\nfinal ledger:")
    print(json.dumps(led.to_dict(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
