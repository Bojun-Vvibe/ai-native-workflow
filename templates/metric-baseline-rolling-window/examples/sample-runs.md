# Sample runs: same data, three scorers, three winners

Three small synthetic datasets, each scored by all three methods.
Each example shows which method gives the operationally correct
answer and why.

The sample series and scores below were produced by running
`lib/baselines.py` directly. To reproduce, copy each `series` into
a Python REPL with `from lib.baselines import score_zscore,
score_mad, score_ewma`.

---

## Example 1 — Stationary metric (z-score wins)

A cache hit rate on a stable workload. Values bounce in a narrow
band around 0.78. Today is 0.79 (boring) and a hypothetical
"weird" day at 0.55.

```python
series_normal = [
    ("2026-04-17", 0.78),
    ("2026-04-18", 0.79),
    ("2026-04-19", 0.77),
    ("2026-04-20", 0.78),
    ("2026-04-21", 0.80),
    ("2026-04-22", 0.78),
    ("2026-04-23", 0.79),
    ("2026-04-24", 0.79),  # today, boring
]
series_weird = series_normal[:-1] + [("2026-04-24", 0.55)]
```

| Series | zscore | mad | ewma |
|---|---|---|---|
| normal | clean (z≈0.59) | clean (≈0.67) | clean (≈0.51) |
| weird  | anomaly (z≈-24) | anomaly (≈-15.5) | anomaly (≈-24.5) |

All three methods catch the weird day; all three correctly leave
the normal day alone. **z-score wins by simplicity** — the
explanation it produces ("0.55 is 24 stdev below the 7-day mean
0.785") is the most legible to a human reading an alert.

---

## Example 2 — Bursty metric with a single big day in baseline (MAD wins)

Daily token spend. Mostly ~100k. One launch-day spike of 10M sits
inside the baseline window. Today is back to 200k — a clear
doubling vs the calm baseline, but z-score will miss it because
that one 10M day inflated stdev.

```python
series = [
    ("2026-04-10",   100_000),
    ("2026-04-11",    98_000),
    ("2026-04-12",   102_000),
    ("2026-04-13",    99_000),
    ("2026-04-14",   101_000),
    ("2026-04-15",   100_000),
    ("2026-04-16",   103_000),
    ("2026-04-17",    97_000),
    ("2026-04-18",   100_000),
    ("2026-04-19",   102_000),
    ("2026-04-20", 10_000_000),  # launch-day spike
    ("2026-04-21",   100_000),
    ("2026-04-22",    99_000),
    ("2026-04-23",   101_000),
    ("2026-04-24",   200_000),   # today: 2x calm baseline
]
```

Approximate scores (window 14):

| Method | Score for today | Verdict |
|---|---|---|
| zscore | ≈ -0.23 (one spike inflated stdev to ~2.5M, swamping the 100k vs 200k difference) | clean |
| mad    | ≈ 67 (median ~100k, MAD ~1k → sigma_mad ~1.5k → today ~67σ above) | anomaly |
| ewma   | ≈ -0.27 (the spike pulled the EWMA up so today looks slightly low rather than high) | clean (with threshold 2.0) |

**MAD wins.** The launch-day spike is real history but it should
not silence the alerter. MAD's median-based center is unmoved by
single spikes.

If you only ever ran z-score on this metric, you'd see a 2× day
slip past silently — and probably not notice for weeks.

---

## Example 3 — Slowly drifting metric (EWMA wins on noise, not on the spike)

p95 latency creeping up over a month, then a sharp deploy-induced
spike today. With this much drift, *all three methods catch the
spike*. The interesting question is **what happens on a normal
drift day** — that's where false positives live.

```python
# 40 days of linear drift from ~120 to ~158.5
drift_only = [(f"2026-03-{i:02d}", 100 + i * 1.5) for i in range(15, 32)] + \
             [(f"2026-04-{i:02d}", 100 + (15 + i) * 1.5) for i in range(1, 25)]
# Same series, last day replaced with a deploy-induced spike.
with_spike = drift_only[:-1] + [("2026-04-24", 280)]
```

Drift-only (today is just continuing the trend; should be `clean`):

| Method | Score | Verdict | Comment |
|---|---|---|---|
| zscore (window 7) | 1.85 | clean | **Dangerously close to threshold 2.0.** Any week where drift accelerates slightly will start firing. |
| zscore (window 30) | 1.96 | clean | Even closer to 2.0. The longer baseline pulls the mean down further, so today looks more anomalous. |
| ewma (span 10) | 1.08 | clean | Comfortably clean. The EWMA is currently tracking ~155; today (~158) is inside one EWMSD. |

With deploy-induced spike (`280`):

| Method | Score | Verdict |
|---|---|---|
| zscore (window 7) | 39.35 | anomaly |
| zscore (window 30) | 15.45 | anomaly |
| ewma (span 10) | 17.51 | anomaly |

**EWMA wins** — not because it catches the spike (everything does)
but because it *doesn't fire on every drift day*. The z-score
methods sit at 1.85–1.96 on a perfectly normal drift day, which
means a slight uptick in the drift rate will push them over 2.0
and produce a false positive. EWMA is sitting at 1.08, with
plenty of headroom.

---

## Takeaway

There is no universally best scorer. The three methods have
opinions about *what shape of normal looks like*:

- z-score: "normal is a narrow band around a moving mean."
- mad:     "normal is whatever the median has been; outliers in
            the baseline are not allowed to redefine normal."
- ewma:    "normal is what the very recent past predicts; slow
            drift is part of normal."

Pick the opinion that matches your metric. The wrong opinion is
the most common cause of alerter noise.
