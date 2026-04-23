"""Tests for baselines.py — happy path, edge cases, and documented contracts."""

import math
import os
import sys
import unittest

# Allow `python3 -m unittest lib.test_baselines` from the template root.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.baselines import (  # noqa: E402
    score_zscore,
    score_mad,
    score_ewma,
    score_zscore_zero_aware,
)


def _series(values, start_day=1):
    """Build a chronological series with synthetic YYYY-MM-DD dates."""
    return [(f"2026-04-{start_day + i:02d}", v) for i, v in enumerate(values)]


class TestZscore(unittest.TestCase):
    def test_clean_within_baseline(self):
        s = _series([100, 102, 98, 101, 99, 103, 100, 101])  # last is "today"
        v = score_zscore(s, window_days=7, threshold=2.0)
        self.assertEqual(v["verdict"], "clean")
        self.assertLess(abs(v["score"]), 2.0)

    def test_obvious_anomaly(self):
        s = _series([100, 102, 98, 101, 99, 103, 100, 500])
        v = score_zscore(s, window_days=7, threshold=2.0)
        self.assertEqual(v["verdict"], "anomaly")
        self.assertGreater(v["score"], 2.0)

    def test_insufficient_data(self):
        s = _series([100, 200])  # baseline is just one value
        v = score_zscore(s, window_days=7)
        self.assertEqual(v["verdict"], "insufficient_data")
        self.assertIsNone(v["score"])

    def test_constant_baseline_today_matches(self):
        s = _series([50, 50, 50, 50, 50, 50, 50, 50])
        v = score_zscore(s, window_days=7)
        self.assertEqual(v["verdict"], "clean")
        self.assertEqual(v["score"], 0.0)

    def test_constant_baseline_today_differs(self):
        s = _series([50, 50, 50, 50, 50, 50, 50, 51])
        v = score_zscore(s, window_days=7)
        self.assertEqual(v["verdict"], "anomaly")
        self.assertEqual(v["score"], math.inf)

    def test_negative_anomaly(self):
        s = _series([100, 102, 98, 101, 99, 103, 100, 0])
        v = score_zscore(s, window_days=7)
        self.assertEqual(v["verdict"], "anomaly")
        self.assertLess(v["score"], -2.0)

    def test_threshold_respected(self):
        # Same data, two thresholds; a borderline z should flip.
        s = _series([100, 102, 98, 101, 99, 103, 100, 110])
        z2 = score_zscore(s, window_days=7, threshold=2.0)
        z3 = score_zscore(s, window_days=7, threshold=3.0)
        # The score is the same; the verdict can differ.
        self.assertAlmostEqual(z2["score"], z3["score"])
        if abs(z2["score"]) >= 2.0 and abs(z2["score"]) < 3.0:
            self.assertEqual(z2["verdict"], "anomaly")
            self.assertEqual(z3["verdict"], "clean")

    def test_window_must_be_at_least_two(self):
        with self.assertRaises(ValueError):
            score_zscore(_series([1, 2]), window_days=1)

    def test_nan_rejected(self):
        with self.assertRaises(ValueError):
            score_zscore(_series([1.0, float("nan"), 3.0]))

    def test_string_rejected(self):
        with self.assertRaises(TypeError):
            score_zscore([("d1", "100"), ("d2", "101")])  # type: ignore[list-item]

    def test_empty_series_rejected(self):
        with self.assertRaises(ValueError):
            score_zscore([])


class TestMad(unittest.TestCase):
    def test_robust_to_single_spike_in_baseline(self):
        # 13 normal days + one massive spike in baseline + a moderate
        # value today. Z-score over the same data would consider
        # today "clean" because the spike inflated stdev. MAD shouldn't.
        baseline = [100] * 13 + [10_000]   # spike on day 14 (last in baseline)
        today = 200
        s = _series(baseline + [today], start_day=1)

        z = score_zscore(s, window_days=14, threshold=2.0)
        m = score_mad(s, window_days=14, threshold=2.0)

        # Z-score: stdev is huge → today's |z| is small → "clean"
        self.assertEqual(z["verdict"], "clean")
        # MAD: median is 100, MAD is 0 → today != median → anomaly (inf)
        self.assertEqual(m["verdict"], "anomaly")

    def test_clean_within_window(self):
        s = _series([100, 102, 98, 101, 99, 103, 100, 102, 99, 101, 100, 102, 99, 101, 100])
        v = score_mad(s, window_days=14)
        self.assertEqual(v["verdict"], "clean")

    def test_insufficient_data(self):
        s = _series([10, 20])
        v = score_mad(s, window_days=14)
        self.assertEqual(v["verdict"], "insufficient_data")


class TestEwma(unittest.TestCase):
    def test_drift_absorbed_spike_caught(self):
        # Slow drift from 100 → 130 over 20 days, then a 500 spike.
        drift = [100 + i * 1.5 for i in range(20)]
        s = _series(drift + [500])
        v = score_ewma(s, span=10, threshold=2.0)
        self.assertEqual(v["verdict"], "anomaly")
        self.assertGreater(v["score"], 2.0)

    def test_drift_alone_not_anomaly(self):
        # Same drift; today continues the drift trend.
        drift = [100 + i * 1.5 for i in range(21)]
        s = _series(drift)
        v = score_ewma(s, span=10, threshold=2.0)
        self.assertEqual(v["verdict"], "clean")

    def test_insufficient_data(self):
        s = _series([1, 2, 3, 4])
        v = score_ewma(s, span=10)
        self.assertEqual(v["verdict"], "insufficient_data")

    def test_span_must_be_at_least_two(self):
        with self.assertRaises(ValueError):
            score_ewma(_series([1, 2, 3]), span=1)


class TestZeroAware(unittest.TestCase):
    def test_all_zero_baseline_today_zero_is_clean(self):
        s = _series([0, 0, 0, 0, 0, 0, 0, 0])
        v = score_zscore_zero_aware(s, window_days=7)
        self.assertEqual(v["verdict"], "clean")
        self.assertEqual(v["score"], 0.0)

    def test_all_zero_baseline_today_positive_is_anomaly(self):
        s = _series([0, 0, 0, 0, 0, 0, 0, 1])
        v = score_zscore_zero_aware(s, window_days=7)
        self.assertEqual(v["verdict"], "anomaly")
        self.assertEqual(v["score"], math.inf)
        self.assertIn("zero-aware", v["explanation"])

    def test_falls_back_to_zscore_when_baseline_has_variance(self):
        s = _series([0, 0, 1, 0, 2, 0, 0, 0])
        v_aware = score_zscore_zero_aware(s, window_days=7)
        v_plain = score_zscore(s, window_days=7)
        self.assertEqual(v_aware["verdict"], v_plain["verdict"])
        self.assertEqual(v_aware["score"], v_plain["score"])


if __name__ == "__main__":
    unittest.main()
