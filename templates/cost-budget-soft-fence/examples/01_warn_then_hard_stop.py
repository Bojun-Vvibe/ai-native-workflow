"""Worked example 1 — staged warns at 60/85/95 then a hard stop at 100.

Budget = $1.00, warn rungs = (0.60, 0.85, 0.95).

We charge a sequence of small spends and observe:
  - Each rung warns exactly once.
  - A spend that would push past $1.00 is rejected as ``hard_stop``
    and is NOT appended to the ledger (running total unchanged).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fence import Ledger, Spend


def main() -> None:
    led = Ledger(budget_usd=1.00)
    schedule = [
        ("c1", 0.20, "ok, no rung yet"),
        ("c2", 0.30, "lands at 0.50, still no warn"),
        ("c3", 0.15, "lands at 0.65 — crosses 60% rung"),
        ("c4", 0.05, "lands at 0.70 — between rungs, ok"),
        ("c5", 0.20, "lands at 0.90 — crosses 85%"),
        ("c6", 0.06, "lands at 0.96 — crosses 95%"),
        ("c7", 0.10, "would push to 1.06 — hard_stop, REJECTED"),
        ("c8", 0.04, "exactly fills budget to 1.00 — ok (no rung above 95% to cross)"),
    ]
    for call_id, amount, note in schedule:
        v = led.charge(Spend(call_id, amount, note))
        print(f"charge {call_id} ${amount:.2f} ({note}):")
        print(" ", json.dumps(v.to_dict(), sort_keys=True))

    print("\nfinal ledger:")
    print(json.dumps(led.to_dict(), indent=2, sort_keys=True))

    # Structural assertions so the example self-checks.
    assert abs(led.spent_usd - 1.00) < 1e-9, led.spent_usd
    assert "c7" not in led.committed, "rejected spend must not be appended"
    assert led.warned_rungs == {0.60, 0.85, 0.95}, led.warned_rungs


if __name__ == "__main__":
    main()
