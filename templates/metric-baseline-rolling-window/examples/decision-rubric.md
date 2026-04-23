# Decision rubric: which baseline method?

A short flowchart for picking the right scorer for a given metric.
Use this when adding a new metric to your alerter; do not pick by
habit or "whatever the last metric used."

## The questions

1. **Is the metric often exactly zero?**
   (e.g., critical-error count, security-policy-violation count,
   queue-overflow count.)
   → **`score_zscore_zero_aware`**.
   No further questions; the other methods misbehave on
   degenerate-zero baselines.

2. **Does the metric have a clear weekly cycle?**
   (e.g., requests/minute on a B2B service, build minutes on a
   weekday-only CI.)
   → See `seasonal-baseline.md` first; come back here only after
   you've decided on a per-day-of-week or business-day-only
   baseline. Then apply step 3 within that filtered baseline.

3. **Does the metric drift slowly day-over-day?**
   ("Slowly" = a few percent per week.)
   - Yes → **`score_ewma`**. EWMA absorbs the drift; today is
     scored against where the metric *should be now*, not where
     it was three weeks ago.
   - No → continue.

4. **Is the metric heavy-tailed?**
   (Token spend during launch weeks, request bursts during
   incidents — anything where one bad day can make stdev useless.)
   - Yes → **`score_mad`**. The median is unmoved by a single
     spike in the baseline, so subsequent real anomalies are
     still detectable.
   - No → continue.

5. **Default:** **`score_zscore`**. Stationary, well-behaved
   metric; the simplest scorer is the right one.

## Worked picks

| Metric | Pick | Why |
|---|---|---|
| Daily token spend on a stable workload | zscore | Stationary, low tail. |
| Daily token spend during product launch | mad | One launch day shouldn't blind you for the next two weeks. |
| Cache hit rate (already a ratio in [0, 1]) | zscore | Stationary; ratios rarely have heavy tails. |
| p95 request latency on a slow-growing service | ewma | Absorbs the slow growth; catches the spike. |
| Critical-error count | zscore_zero_aware | Often exactly zero; can't divide by zero stdev. |
| Build minutes on a weekday-only CI | seasonal + zscore | Filter to weekdays first. |
| Number of agent retries per day | mad or zero_aware | Bursty *and* often zero; pick zero_aware if the zero days dominate, MAD if the non-zero days dominate. |

## What to do when the rubric is ambiguous

Run the metric through **all three** methods (plus zero-aware if
applicable) for two weeks. Log every verdict. Compare against the
ground truth ("did this day actually warrant a human's attention?").
The method with the best F1 wins.

If two methods tie on F1, pick the one with the **smaller
explanation** — the alerter has to write the message a tired human
will read at 9:05 in the morning. Shorter wins.
