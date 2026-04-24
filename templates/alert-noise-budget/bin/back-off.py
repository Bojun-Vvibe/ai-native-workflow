#!/usr/bin/env python3
"""back-off.py — apply the two-strikes back-off rule to a detector's fire history.

Given a detector's per-day fire log (CSV with date,fired) and a per-week budget,
walk forward week by week and decide for each week:

  - within budget  → status: ok
  - over budget    → status: warn  (first strike)
  - over 2 in a row → status: mute (silence detector for one week)
  - mute window expired → status: recalibrate (compute new threshold from new history)

Emit one line per week. This is a reference implementation of §4 of BUDGET.md.

Usage:
    python3 back-off.py --fires fires.csv --budget-per-week 1
"""
from __future__ import annotations

import argparse
import csv
import datetime
import sys


def week_index(d: datetime.date, anchor: datetime.date) -> int:
    return (d - anchor).days // 7


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fires", required=True, help="CSV with date,fired (fired ∈ {0,1})")
    ap.add_argument("--budget-per-week", type=float, default=1.0)
    args = ap.parse_args()

    with open(args.fires, newline="") as fh:
        rows = list(csv.DictReader(fh))
    if not rows:
        print("no rows in fires file", file=sys.stderr)
        return 1

    by_week: dict[int, int] = {}
    anchor = datetime.date.fromisoformat(rows[0]["date"])
    week_start: dict[int, datetime.date] = {}
    for r in rows:
        d = datetime.date.fromisoformat(r["date"])
        wi = week_index(d, anchor)
        by_week[wi] = by_week.get(wi, 0) + int(r["fired"])
        if wi not in week_start:
            week_start[wi] = d

    state = "ok"
    consecutive_over = 0
    muted_until_week: int | None = None
    over_threshold = args.budget_per_week  # over-budget if fires > budget

    print(f"budget: {args.budget_per_week:g} fires/week (over-budget if fires > {over_threshold:g})")
    print()
    print(f"  {'week':4s} {'start':10s} {'fires':>5s}  {'state':12s}  action")
    print(f"  {'----':4s} {'----------':10s} {'-----':>5s}  {'------------':12s}  ---------------------------")

    for wi in sorted(by_week):
        fires = by_week[wi]
        if muted_until_week is not None and wi < muted_until_week:
            state = "muted"
            action = f"silenced (re-eval week {muted_until_week})"
        elif muted_until_week is not None and wi == muted_until_week:
            state = "recalibrate"
            action = "mute window expired; re-calibrate threshold from current history"
            muted_until_week = None
            consecutive_over = 0
        elif fires > over_threshold:
            consecutive_over += 1
            if consecutive_over >= 2:
                state = "mute"
                muted_until_week = wi + 1
                action = f"two strikes — mute for week {wi + 1}"
            else:
                state = "warn"
                action = "first strike — investigate but keep firing"
        else:
            state = "ok"
            consecutive_over = 0
            action = ""

        print(f"  {wi:4d} {week_start[wi].isoformat()} {fires:>5d}  {state:12s}  {action}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
