#!/usr/bin/env python3
"""merge-budget.py — project the OR-merged alert rate of N detectors against shared history.

Given a CSV with one date column and N metric columns, plus N detector specs of the form
`<column>:<scorer>:<threshold>`, simulate each detector across the history window, then
report:

  - per-detector fire count
  - naive sum (what a noise-blind operator would expect)
  - actual OR-merged fire count (days when ANY detector fires)
  - empirical pairwise correlations between detector fire-day indicators

This is the script you run BEFORE adding a new detector to a shared channel, to confirm
you won't blow the channel's aggregate alert budget.

Usage:
    python3 merge-budget.py --history history.csv --window 28 \\
        --detector "ratio:zscore:2.41" \\
        --detector "tokens:zscore:2.18"

Stdlib only.
"""
from __future__ import annotations

import argparse
import csv
import sys
from typing import List

# Re-use scorers from calibrate.py via path-local import.
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from calibrate import SCORERS  # noqa: E402


def parse_detector(spec: str) -> tuple[str, str, float]:
    parts = spec.split(":")
    if len(parts) != 3:
        raise SystemExit(f"bad --detector spec {spec!r}; want 'column:scorer:threshold'")
    column, scorer, threshold = parts
    if scorer not in SCORERS:
        raise SystemExit(f"unknown scorer {scorer!r}; have {sorted(SCORERS)}")
    return column, scorer, float(threshold)


def load_columns(path: str, columns: List[str]) -> dict[str, List[float]]:
    with open(path, newline="") as fh:
        reader = csv.DictReader(fh)
        missing = [c for c in columns if c not in (reader.fieldnames or [])]
        if missing:
            raise SystemExit(f"missing columns {missing} in {path}; have {reader.fieldnames}")
        out: dict[str, List[float]] = {c: [] for c in columns}
        for row in reader:
            for c in columns:
                if row[c] == "":
                    continue
                out[c].append(float(row[c]))
    return out


def correlation(a: List[int], b: List[int]) -> float:
    """Pearson correlation between two 0/1 indicator series."""
    n = len(a)
    if n == 0 or len(b) != n:
        return 0.0
    mean_a = sum(a) / n
    mean_b = sum(b) / n
    num = sum((a[i] - mean_a) * (b[i] - mean_b) for i in range(n))
    den_a = sum((a[i] - mean_a) ** 2 for i in range(n)) ** 0.5
    den_b = sum((b[i] - mean_b) ** 2 for i in range(n)) ** 0.5
    if den_a == 0 or den_b == 0:
        return 0.0
    return num / (den_a * den_b)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--history", required=True)
    ap.add_argument("--window", type=int, default=28)
    ap.add_argument("--detector", action="append", required=True,
                    help="column:scorer:threshold (repeatable)")
    args = ap.parse_args()

    detectors = [parse_detector(s) for s in args.detector]
    columns = sorted({d[0] for d in detectors})
    data = load_columns(args.history, columns)

    # Truncate every column to the same trailing window.
    n = min(len(v) for v in data.values())
    if n < args.window:
        print(f"warning: history has only {n} rows, using all", file=sys.stderr)
        window = n
    else:
        window = args.window
    for c in columns:
        data[c] = data[c][-window:]

    # Score each detector and produce a fire-indicator series.
    fires: List[List[int]] = []
    print(f"window: {window} days, {len(detectors)} detectors")
    print()
    for column, scorer_name, threshold in detectors:
        scorer = SCORERS[scorer_name]
        scores = scorer(data[column])
        indicator = [1 if abs(s) >= threshold else 0 for s in scores]
        fires.append(indicator)
        print(f"  {column:20s} {scorer_name:6s} threshold={threshold:.3f}  fired {sum(indicator)}/{window} days")

    # Naive sum vs actual OR-merge.
    naive_sum = sum(sum(f) for f in fires)
    or_merged = sum(1 for i in range(window) if any(f[i] for f in fires))
    print()
    print(f"  naive sum of fires:      {naive_sum}/{window} days  (what a noise-blind operator expects)")
    print(f"  actual OR-merged fires:  {or_merged}/{window} days  (what the channel actually receives)")
    saved = naive_sum - or_merged
    if saved > 0:
        print(f"  collapsed {saved} fires (positive correlation between detectors — cheap merge)")
    elif saved == 0:
        print(f"  no collapse — detectors fire on disjoint days (worst case for channel load)")

    # Pairwise correlations.
    if len(detectors) > 1:
        print()
        print("  pairwise correlation of fire-day indicators:")
        for i in range(len(detectors)):
            for j in range(i + 1, len(detectors)):
                r = correlation(fires[i], fires[j])
                tag = "+" if r > 0 else ("-" if r < 0 else " ")
                print(f"    {detectors[i][0]:15s} <-> {detectors[j][0]:15s}  r = {tag}{abs(r):.2f}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
