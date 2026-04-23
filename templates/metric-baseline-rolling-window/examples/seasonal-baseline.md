# Seasonal baseline (extension recipe)

A rolling-window baseline assumes the metric is stationary across
the days in the window. That assumption breaks for metrics with a
clear weekly cycle — for example, daily token spend on a workload
that runs primarily Mon–Fri. A naive 7-day window will:

- Alert every Monday because the weekend dragged the baseline down.
- Quietly accept a real Saturday spike because the baseline already
  contains other low-traffic Saturdays.

The fix is **don't pool different days of the week into one
baseline.** Score each day against same-day-of-week history.

## The minimal change

Filter the baseline to days of the week that match today before
calling `score_zscore` (or any other scorer):

```python
import datetime as dt
from lib.baselines import score_zscore

def score_seasonal(series, weeks=4, threshold=2.0):
    """Score today vs the same-day-of-week from the last `weeks` weeks.

    `series` is the same (date_str_YYYY_MM_DD, value) shape as the
    other scorers. Returns the same verdict dict shape.
    """
    today_date_str, today_value = series[-1]
    today_dow = dt.date.fromisoformat(today_date_str).weekday()

    same_dow = [
        (d, v) for (d, v) in series[:-1]
        if dt.date.fromisoformat(d).weekday() == today_dow
    ][-weeks:]  # last `weeks` matching days

    filtered = same_dow + [series[-1]]
    return score_zscore(filtered, window_days=len(same_dow), threshold=threshold)
```

Four weeks of same-day-of-week history is the minimum viable
baseline (3 prior + today). Six to eight weeks is more comfortable.

## Caveats

- **Holidays still break it.** A Thanksgiving Thursday is not a
  representative Thursday. If your workload has holidays, either
  exclude known holidays from the baseline or accept the false
  positives on holiday-adjacent days.
- **First seasonal alerter is noisy.** You'll discover that
  "Tuesdays at 14:00" looks different from "Tuesdays at 09:00"
  for hourly metrics. Daily metrics avoid that, which is one
  reason this template targets daily granularity.
- **Don't compose seasonal with EWMA naively.** EWMA already tries
  to track drift; layering same-day-of-week on top makes the
  scorer hard to reason about. Pick one or the other.

## When to skip seasonality entirely

- The metric *is* stationary (truly: cache hit rate on a 24/7
  service, error rate on a multi-region service that doesn't sleep).
- You have less than 4 weeks of history (the seasonal baseline
  starves; the regular trailing baseline does not).
- The metric is already aggregated weekly. There's nothing seasonal
  to remove from a weekly time series.
