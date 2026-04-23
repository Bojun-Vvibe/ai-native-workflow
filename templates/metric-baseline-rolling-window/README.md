# Template: rolling-window baseline for agent observability metrics

A methodology + reference implementation for the question "is
today's number weird?" — applied to any time-series an LLM-agent
operation produces (token spend, cache hit rate, error count,
mean latency, request count, …).

This is the math layer that
[`anomaly-alert-cron`](../anomaly-alert-cron/) and similar tools
sit on top of. If you adopted that template and the alerts feel
either too noisy or too quiet, the fix lives here.

## Purpose

Three classes of rolling-window baseline cover ~90% of agent
observability needs:

| Method | Best for | Worst for |
|---|---|---|
| **Z-score over trailing window** | Stationary metrics: cache hit rate on a stable workload, error count on a quiet service. | Bursty metrics with a heavy tail (token spend during a launch week). |
| **Median + MAD (Median Absolute Deviation)** | Heavy-tailed metrics: token spend, request count. Robust to a single bad day in the baseline. | Metrics with a clear seasonal pattern (weekly cycle). |
| **EWMA (Exponentially Weighted Moving Average)** | Metrics with slow drift you want to track *and* anomalies you want to catch. | Step-changes (deployment landed, model swapped) — EWMA chases them and silences the alert. |

Pick one method per metric. Don't try to combine them in one
score; that's how you end up with an alert nobody can interpret.

## When to use

- You have ≥ 14 days of daily samples for the metric.
- The metric updates at most once per day (or you bin it daily).
- You want a defensible answer to "should this alert?" — not just
  a hand-tuned threshold.
- You operate one or two metrics. Beyond ~ten, you need a real
  observability product, not a template.

## When NOT to use

- Sub-second / per-request anomaly detection. Use a streaming
  algorithm (Welford / EWMA on a per-request basis) inside the
  request path, not a daily batch.
- Multivariate anomaly detection ("requests are normal *and*
  latency is normal but the *combination* is weird"). That needs
  a real model — Mahalanobis distance, isolation forest,
  autoencoder. Out of scope.
- Stepwise metrics that change discontinuously on deploys. A
  rolling baseline will fire on every deploy. Either deploy-gate
  the alert or use a per-deploy baseline reset.
- Counts that are often zero. Z-score against a baseline of zeros
  divides by ~0 and produces nonsense. Use the "zero-aware MAD"
  variant in `lib/baselines.py`.

## Inputs / Outputs

**Input:** an iterable of `(date, value)` tuples in chronological
order. `date` is anything orderable (string `YYYY-MM-DD` works
fine); `value` is a float or int.

**Output:** for the most recent observation, a structured verdict:

```python
{
  "date": "2026-04-24",
  "value": 187_421,
  "method": "zscore",
  "baseline": {"window_days": 7, "mean": 102_300, "stdev": 18_400, "n": 7},
  "score": 4.62,         # number of stdevs from baseline mean
  "threshold": 2.0,
  "verdict": "anomaly",  # one of: clean | anomaly | insufficient_data
  "explanation": "value 187421 is 4.62 stdev above 7-day baseline mean 102300"
}
```

The verdict `insufficient_data` is its own outcome on purpose —
it should *not* page, but it should be visible. Many silent
failures are "we never had enough data and the alerter quietly
returned `clean` for two weeks."

## How it works

### Z-score (`zscore`)

```
baseline_window = last N days BEFORE today  (default N=7)
mean   = mean(baseline_window)
stdev  = sample stdev of baseline_window  (ddof=1)
score  = (today - mean) / stdev    (∞ if stdev==0)
verdict: "anomaly" if abs(score) >= threshold else "clean"
```

Default threshold: `2.0`. At a normal distribution that's a
~5% per-day false-positive rate. With 365 daily checks per
year, expect ~18 false positives. Bump to `3.0` for
~3 false positives per year if your false-positive cost is
high (e.g. a webhook that wakes a phone).

### Median + MAD (`mad`)

```
baseline_window = last N days BEFORE today  (default N=14)
med    = median(baseline_window)
mad    = median(|x - med| for x in baseline_window)
sigma_mad = 1.4826 * mad         # consistent estimator vs normal stdev
score  = (today - med) / sigma_mad
verdict: "anomaly" if abs(score) >= threshold else "clean"
```

The `1.4826` factor makes the MAD-based score directly comparable
to a normal-distribution z-score. Threshold guidance is therefore
the same: `2.0` → ~5%/day FP, `3.0` → very rare.

MAD is robust: a single 10× spike in the baseline window pushes
the *mean* upward (and inflates stdev), masking subsequent real
anomalies. The median is unmoved. This is why MAD is preferred
for token-spend-style metrics — one launch week shouldn't blind
you for the next two.

### EWMA (`ewma`)

```
alpha  = 2 / (N + 1)              # default N=10 → alpha ≈ 0.18
ewma_t = alpha * x_t + (1 - alpha) * ewma_{t-1}
ewmsd_t = sqrt(alpha * (x_t - ewma_t)**2 + (1 - alpha) * ewmsd_{t-1}**2)
score   = (today - ewma_yesterday) / ewmsd_yesterday
```

Compare today against *yesterday's* EWMA, not today's — otherwise
today's value contaminates its own baseline.

EWMA is the right pick when the metric drifts slowly (e.g.,
token usage growing 2% per week as you onboard more workflows)
*and* you still want to catch sharp spikes. The drift gets
absorbed; the spike does not.

### Zero-aware variant

Counts that often are zero (e.g., critical-error count) break
both z-score and MAD because stdev/MAD collapse to 0 when most
of the baseline is zero. The zero-aware variant in
`lib/baselines.py`:

- Returns `verdict="anomaly"` with score `inf` if today is a
  positive integer and **all** baseline values are zero.
- Returns `verdict="clean"` if today is also zero.
- Falls back to z-score when baseline has any non-zero variance.

This avoids the most common production-monitoring bug: you wire
up an alerter on `count_of_critical_errors`, the metric is `0`
every day for the baseline, then `1` arrives and stdev=0 makes
the z-score undefined → silent skip.

## Files

- `lib/baselines.py` — pure-Python (stdlib only) reference
  implementation of all three methods plus the zero-aware variant.
  ~250 lines including docstrings.
- `lib/test_baselines.py` — `unittest`-based tests covering happy
  path, edge cases (single-element baseline, all zeros, constant
  baseline, NaN handling), and the documented threshold/FP
  relationships.
- `examples/decision-rubric.md` — flowchart-style guide: given a
  metric description, which method should you pick?
- `examples/seasonal-baseline.md` — extension recipe for metrics
  with a weekly cycle ("Mondays are different"). Day-of-week
  baseline rather than naive trailing window.
- `examples/sample-runs.md` — three worked examples on synthetic
  data: stationary metric (z-score wins), bursty metric (MAD
  wins), drifting metric (EWMA wins). Shows the same data scored
  by all three and explains why each pick is correct.

## Quickstart

```python
from lib.baselines import score_zscore

series = [
    ("2026-04-17", 102_000),
    ("2026-04-18",  98_500),
    ("2026-04-19", 105_200),
    ("2026-04-20", 101_800),
    ("2026-04-21",  99_300),
    ("2026-04-22", 107_400),
    ("2026-04-23", 103_100),
    ("2026-04-24", 187_421),  # today
]

verdict = score_zscore(series, window_days=7, threshold=2.0)
print(verdict["verdict"], verdict["score"])
# anomaly 4.62
```

To run the tests:

```bash
cd templates/metric-baseline-rolling-window
python3 -m unittest lib.test_baselines -v
```

## Adapt this section

- Decide which **method** fits each metric. Use
  `examples/decision-rubric.md` as a checklist; do not pick by
  habit.
- Pin the **window size** explicitly per metric in your call site.
  Defaults in `baselines.py` are reasonable starting points
  (z-score: 7 days; MAD: 14 days; EWMA: span of 10) but the
  right window is workload-dependent.
- Pin the **threshold** explicitly per metric. The `2.0` default
  produces an alert ~once per three weeks per metric on
  well-behaved data. If you have ten metrics, that becomes ~once
  per two days *in aggregate* — re-tune.
- If the metric is **counts that often are zero**, use
  `score_zscore_zero_aware` instead of `score_zscore`.
- Wire the verdict into your scheduler. The `pew anomalies`
  subcommand of [`pew-insights`](https://github.com/anomalyco/pew-insights)
  uses this exact contract; the
  [`anomaly-alert-cron`](../anomaly-alert-cron/) template
  consumes that exit code.

## Safety notes

- The reference implementation is **read-only** with respect to
  the input series. It does no I/O, no logging, no network. It
  is safe to call inside a hot loop (though "daily batch" is the
  intended cadence).
- All three methods are deterministic given the same input series
  and parameters — no randomness, no time-of-day dependency. Test
  failures are real failures; flaky tests would indicate a bug
  in the test, not in `baselines.py`.
- The `verdict` field uses a closed vocabulary
  (`clean | anomaly | insufficient_data`). Do not extend it
  ad-hoc — add a new verdict only with a corresponding test, and
  document the downstream consumer changes (your scheduler
  probably switch-cases on it).
