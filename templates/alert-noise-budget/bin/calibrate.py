#!/usr/bin/env python3
"""calibrate.py — pick a detector threshold from a metric history and a target budget.

Given a CSV file with a 'date' column and one numeric metric column, score every day
with a chosen scorer (zscore | mad | ewma), then return the threshold that would have
produced exactly `budget` alerts across the calibration window.

Usage:
    python3 calibrate.py --history history.csv --metric value \\
        --scorer zscore --window 28 --budget-per-week 1

Stdlib only. No external deps. Tested under Python 3.10+.
"""
from __future__ import annotations

import argparse
import csv
import math
import statistics
import sys
from typing import Callable, List


def score_zscore(values: List[float]) -> List[float]:
    """Z-score of each value vs the mean/stdev of *all other* values.

    Leave-one-out so a single outlier does not absorb itself.
    """
    n = len(values)
    if n < 3:
        return [0.0] * n
    out: List[float] = []
    total = sum(values)
    total_sq = sum(v * v for v in values)
    for v in values:
        rest_n = n - 1
        rest_mean = (total - v) / rest_n
        rest_var = max(0.0, (total_sq - v * v) / rest_n - rest_mean * rest_mean)
        rest_std = math.sqrt(rest_var)
        if rest_std == 0:
            out.append(0.0)
        else:
            out.append((v - rest_mean) / rest_std)
    return out


def score_mad(values: List[float]) -> List[float]:
    """Modified z-score using median + median absolute deviation. Robust to outliers."""
    if len(values) < 3:
        return [0.0] * len(values)
    med = statistics.median(values)
    abs_dev = [abs(v - med) for v in values]
    mad = statistics.median(abs_dev)
    if mad == 0:
        return [0.0] * len(values)
    # 0.6745 is the consistency constant making MAD comparable to stdev under normality.
    return [0.6745 * (v - med) / mad for v in values]


def score_ewma(values: List[float], alpha: float = 0.3) -> List[float]:
    """Score each day as deviation from an EWMA of prior days, normalised by EWMA stdev."""
    n = len(values)
    if n < 3:
        return [0.0] * n
    out: List[float] = [0.0]
    ewma = values[0]
    ewma_var = 0.0
    for i in range(1, n):
        v = values[i]
        std = math.sqrt(ewma_var) if ewma_var > 0 else 0.0
        out.append((v - ewma) / std if std > 0 else 0.0)
        # update AFTER scoring so we score against history not self
        delta = v - ewma
        ewma = ewma + alpha * delta
        ewma_var = (1 - alpha) * (ewma_var + alpha * delta * delta)
    return out


SCORERS: dict[str, Callable[[List[float]], List[float]]] = {
    "zscore": score_zscore,
    "mad": score_mad,
    "ewma": score_ewma,
}


def calibrate(scores: List[float], budget: int) -> tuple[float, int]:
    """Return (threshold, fire_count) such that abs(score) >= threshold fires `budget` times."""
    if budget <= 0:
        return (float("inf"), 0)
    abs_scores = sorted((abs(s) for s in scores), reverse=True)
    if budget > len(abs_scores):
        return (0.0, len(abs_scores))
    threshold = abs_scores[budget - 1]
    fire_count = sum(1 for s in abs_scores if s >= threshold)
    return (threshold, fire_count)


def load_metric(path: str, column: str) -> List[float]:
    with open(path, newline="") as fh:
        reader = csv.DictReader(fh)
        if column not in (reader.fieldnames or []):
            raise SystemExit(f"column {column!r} not in {path}; have {reader.fieldnames}")
        return [float(row[column]) for row in reader if row[column] != ""]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--history", required=True, help="CSV file with metric column")
    ap.add_argument("--metric", default="value", help="column name (default: value)")
    ap.add_argument("--scorer", default="zscore", choices=sorted(SCORERS))
    ap.add_argument("--window", type=int, default=28, help="calibration window in days (default: 28)")
    ap.add_argument("--budget-per-week", type=float, default=1.0, help="target alerts per week (default: 1)")
    args = ap.parse_args()

    values = load_metric(args.history, args.metric)
    if len(values) < args.window:
        print(f"warning: history has {len(values)} rows, requested window {args.window}; using {len(values)}", file=sys.stderr)
        window_values = values
    else:
        window_values = values[-args.window:]

    actual_window = len(window_values)
    budget = max(1, round(args.budget_per_week * actual_window / 7))

    scorer = SCORERS[args.scorer]
    scores = scorer(window_values)
    threshold, fire_count = calibrate(scores, budget)

    print(f"scorer:           {args.scorer}")
    print(f"window:           {actual_window} days")
    print(f"target budget:    {args.budget_per_week:g}/week → {budget} alerts across window")
    print(f"recommended threshold (|score| >=): {threshold:.3f}")
    print(f"would have fired: {fire_count}/{actual_window} days at this threshold")

    if threshold == 0.0:
        print("note: threshold collapsed to 0 — metric too quiet for requested budget", file=sys.stderr)
        return 2
    if threshold > 4.0:
        print("note: threshold > 4.0 — metric is spikier than scorer assumes; consider --scorer mad", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
