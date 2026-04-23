"""
baselines.py — rolling-window baseline scorers for daily time series.

Three methods implemented here:

  - score_zscore(series, window_days=7, threshold=2.0)
  - score_mad(series, window_days=14, threshold=2.0)
  - score_ewma(series, span=10, threshold=2.0)

Plus one robustness wrapper for count metrics that are often zero:

  - score_zscore_zero_aware(series, window_days=7, threshold=2.0)

Conventions
-----------
- `series` is an iterable of (date, value) tuples in chronological
  order. The LAST element is "today". The preceding elements form
  the baseline window.
- Returned verdict is one of: "clean", "anomaly", "insufficient_data".
- The "score" field is the number of stdev (or MAD-equivalent) the
  most recent value sits above (positive) or below (negative) the
  baseline center.
- All inputs are validated; no silent coercion. Pass floats; if
  you pass strings the function raises TypeError.

Stdlib-only by design. No numpy, no pandas. The whole point of
this template is that it drops into any Python project without
adding a dep.
"""

from __future__ import annotations

import math
import statistics
from typing import Iterable, List, Tuple, Sequence


VerdictDict = dict


_VERDICT_CLEAN = "clean"
_VERDICT_ANOMALY = "anomaly"
_VERDICT_INSUFFICIENT = "insufficient_data"


def _split_today(series: Iterable[Tuple[object, float]]) -> Tuple[Tuple[object, float], List[Tuple[object, float]]]:
    """Return (today, baseline_in_chronological_order). Validates input."""
    items: List[Tuple[object, float]] = list(series)
    if not items:
        raise ValueError("series is empty")
    for date, value in items:
        if not isinstance(value, (int, float)):
            raise TypeError(
                f"value for {date!r} must be int or float, got {type(value).__name__}"
            )
        if isinstance(value, float) and math.isnan(value):
            raise ValueError(f"value for {date!r} is NaN")
    today = items[-1]
    baseline = items[:-1]
    return today, baseline


def _insufficient(today_date: object, today_value: float, method: str, **extra) -> VerdictDict:
    return {
        "date": today_date,
        "value": today_value,
        "method": method,
        "verdict": _VERDICT_INSUFFICIENT,
        "score": None,
        "explanation": "baseline window has too few samples to score",
        **extra,
    }


def score_zscore(
    series: Iterable[Tuple[object, float]],
    window_days: int = 7,
    threshold: float = 2.0,
) -> VerdictDict:
    """Z-score of today vs trailing `window_days` days.

    Requires at least 2 samples in the baseline (sample stdev needs
    ddof=1). If stdev is exactly 0 and today differs from the
    baseline mean, returns an anomaly with score = +/-inf.
    """
    if window_days < 2:
        raise ValueError("window_days must be >= 2 for a meaningful stdev")

    (today_date, today_value), baseline_all = _split_today(series)
    baseline = [v for _, v in baseline_all[-window_days:]]

    if len(baseline) < 2:
        return _insufficient(today_date, today_value, "zscore",
                             baseline={"window_days": window_days, "n": len(baseline)})

    mean = statistics.fmean(baseline)
    stdev = statistics.stdev(baseline)  # sample stdev, ddof=1

    if stdev == 0:
        if today_value == mean:
            score = 0.0
            verdict = _VERDICT_CLEAN
        else:
            score = math.inf if today_value > mean else -math.inf
            verdict = _VERDICT_ANOMALY
    else:
        score = (today_value - mean) / stdev
        verdict = _VERDICT_ANOMALY if abs(score) >= threshold else _VERDICT_CLEAN

    direction = "above" if today_value >= mean else "below"
    return {
        "date": today_date,
        "value": today_value,
        "method": "zscore",
        "baseline": {
            "window_days": window_days,
            "mean": mean,
            "stdev": stdev,
            "n": len(baseline),
        },
        "score": score,
        "threshold": threshold,
        "verdict": verdict,
        "explanation": (
            f"value {today_value} is {abs(score):.2f} stdev {direction} "
            f"{window_days}-day baseline mean {mean:.2f}"
        ),
    }


def score_mad(
    series: Iterable[Tuple[object, float]],
    window_days: int = 14,
    threshold: float = 2.0,
) -> VerdictDict:
    """Median + MAD score. Robust to single-day spikes in the baseline.

    Score is normalized by 1.4826 * MAD so the threshold is
    directly comparable to a normal-distribution z-score.
    """
    if window_days < 2:
        raise ValueError("window_days must be >= 2")

    (today_date, today_value), baseline_all = _split_today(series)
    baseline = [v for _, v in baseline_all[-window_days:]]

    if len(baseline) < 2:
        return _insufficient(today_date, today_value, "mad",
                             baseline={"window_days": window_days, "n": len(baseline)})

    med = statistics.median(baseline)
    abs_dev = [abs(v - med) for v in baseline]
    mad = statistics.median(abs_dev)
    sigma_mad = 1.4826 * mad

    if sigma_mad == 0:
        if today_value == med:
            score = 0.0
            verdict = _VERDICT_CLEAN
        else:
            score = math.inf if today_value > med else -math.inf
            verdict = _VERDICT_ANOMALY
    else:
        score = (today_value - med) / sigma_mad
        verdict = _VERDICT_ANOMALY if abs(score) >= threshold else _VERDICT_CLEAN

    direction = "above" if today_value >= med else "below"
    return {
        "date": today_date,
        "value": today_value,
        "method": "mad",
        "baseline": {
            "window_days": window_days,
            "median": med,
            "mad": mad,
            "sigma_mad": sigma_mad,
            "n": len(baseline),
        },
        "score": score,
        "threshold": threshold,
        "verdict": verdict,
        "explanation": (
            f"value {today_value} is {abs(score):.2f} MAD-stdev {direction} "
            f"{window_days}-day baseline median {med:.2f}"
        ),
    }


def score_ewma(
    series: Iterable[Tuple[object, float]],
    span: int = 10,
    threshold: float = 2.0,
) -> VerdictDict:
    """EWMA score. Compares today vs yesterday's EWMA mean and EWMSD.

    Uses the standard alpha = 2 / (span + 1) parameterization so
    `span` reads like an "effective window size" similar to a
    simple moving average.
    """
    if span < 2:
        raise ValueError("span must be >= 2")

    (today_date, today_value), baseline_all = _split_today(series)
    baseline_values = [v for _, v in baseline_all]

    if len(baseline_values) < span:
        return _insufficient(today_date, today_value, "ewma",
                             baseline={"span": span, "n": len(baseline_values)})

    alpha = 2.0 / (span + 1.0)

    # Initialize EWMA with the first value; EWMSD with 0.
    # Iterate over baseline only; we want yesterday's EWMA / EWMSD
    # to score today.
    ewma = baseline_values[0]
    ewmsd_sq = 0.0
    for x in baseline_values[1:]:
        prev_ewma = ewma
        ewma = alpha * x + (1 - alpha) * prev_ewma
        # West / Welford-style EW variance update (one common form):
        ewmsd_sq = alpha * (x - prev_ewma) ** 2 + (1 - alpha) * ewmsd_sq

    ewmsd = math.sqrt(ewmsd_sq)

    if ewmsd == 0:
        if today_value == ewma:
            score = 0.0
            verdict = _VERDICT_CLEAN
        else:
            score = math.inf if today_value > ewma else -math.inf
            verdict = _VERDICT_ANOMALY
    else:
        score = (today_value - ewma) / ewmsd
        verdict = _VERDICT_ANOMALY if abs(score) >= threshold else _VERDICT_CLEAN

    direction = "above" if today_value >= ewma else "below"
    return {
        "date": today_date,
        "value": today_value,
        "method": "ewma",
        "baseline": {
            "span": span,
            "alpha": alpha,
            "ewma": ewma,
            "ewmsd": ewmsd,
            "n": len(baseline_values),
        },
        "score": score,
        "threshold": threshold,
        "verdict": verdict,
        "explanation": (
            f"value {today_value} is {abs(score):.2f} EWMSD {direction} "
            f"yesterday's EWMA {ewma:.2f} (span={span})"
        ),
    }


def score_zscore_zero_aware(
    series: Iterable[Tuple[object, float]],
    window_days: int = 7,
    threshold: float = 2.0,
) -> VerdictDict:
    """Z-score variant safe for count metrics that are often zero.

    Behavior:
      - If today and the entire baseline are exactly zero → clean.
      - If today > 0 and the entire baseline is exactly zero
        → anomaly with score=+inf and an explicit explanation.
      - Otherwise behaves identically to score_zscore.
    """
    if window_days < 2:
        raise ValueError("window_days must be >= 2")

    (today_date, today_value), baseline_all = _split_today(series)
    baseline = [v for _, v in baseline_all[-window_days:]]

    if len(baseline) < 2:
        return _insufficient(today_date, today_value, "zscore_zero_aware",
                             baseline={"window_days": window_days, "n": len(baseline)})

    if all(v == 0 for v in baseline):
        if today_value == 0:
            return {
                "date": today_date,
                "value": today_value,
                "method": "zscore_zero_aware",
                "baseline": {"window_days": window_days, "all_zero": True, "n": len(baseline)},
                "score": 0.0,
                "threshold": threshold,
                "verdict": _VERDICT_CLEAN,
                "explanation": f"baseline is all-zero and today is also zero",
            }
        return {
            "date": today_date,
            "value": today_value,
            "method": "zscore_zero_aware",
            "baseline": {"window_days": window_days, "all_zero": True, "n": len(baseline)},
            "score": math.inf if today_value > 0 else -math.inf,
            "threshold": threshold,
            "verdict": _VERDICT_ANOMALY,
            "explanation": (
                f"baseline is all-zero and today is {today_value}; "
                f"any non-zero value is treated as an anomaly under zero-aware policy"
            ),
        }

    return score_zscore(series, window_days=window_days, threshold=threshold)
