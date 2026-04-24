# Example 01 — single detector, z-score, weekly budget = 1

A stationary metric (request count per day) tracked over 28 days.
We want roughly **one alert per week** — i.e. four alerts over the
calibration window.

## Inputs

- `history.csv` — 28 days of synthetic request-count data. Mostly
  flat around 1000/day, with two genuine outliers near the end.
- Scorer: `zscore` (metric is roughly stationary; no obvious cycle).
- Budget: 1 alert / week → 4 across 28 days.

## Run

```bash
python3 ../../bin/calibrate.py \
    --history history.csv \
    --metric value \
    --scorer zscore \
    --window 28 \
    --budget-per-week 1
```

## Expected output

```
scorer:           zscore
window:           28 days
target budget:    1/week → 4 alerts across window
recommended threshold (|score| >=): 1.185
would have fired: 4/28 days at this threshold
```

(Numbers depend on the exact synthetic draw; structure should match:
threshold around 1.0–1.5, fired exactly 4 days.)

## What this teaches

- "`|z| ≥ 2.0`" would have fired only **1** day here — well under-
  budget. The textbook number was wrong for this metric: at 2.0 you
  miss most weeks and the recipient learns to tune the channel out
  not from noise but from absence.
- The empirically-calibrated threshold (~1.18) is well below the
  textbook number, but produces the desired alert rate of one per
  week. That's the whole point: the rate is what matters, not the
  score.
- The two genuine outliers (day 24 spike, day 27 drop) are both in
  the top-4 absolute scores, so they would fire — along with two
  ordinary days slightly above the calibrated threshold. That's
  intended: a budget of 1/week deliberately includes some
  near-threshold noise so the detector stays "warm".

## What you DO with this number

Wire it into your detector configuration. Re-run calibration once
per budget window (here, weekly). If the new threshold drifts more
than ±20% week over week, the underlying distribution has shifted
and you should investigate the metric, not just re-tune.
