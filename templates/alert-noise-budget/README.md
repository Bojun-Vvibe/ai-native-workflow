# Template: alert-noise-budget

A methodology and small reference toolkit for answering two questions
that always come up the moment you have *more than one* anomaly
detector firing into the same notification channel:

1. **What threshold should each detector fire at, individually?**
2. **What happens when several detectors are OR-merged into a single
   alert stream — and how do you keep the merged stream from
   degenerating into noise?**

This template is the missing third leg of the
`metric-baseline-rolling-window` (the math) +
`anomaly-alert-cron` (the scheduling) pair. Those two tell you *how
to score* a metric and *when to run* the scoring. They do not tell
you *where to put the threshold* or *how many alerts per week is
"too many"*. This template does.

## Why this exists

Two failure modes show up the moment a small operations stack starts
running more than one detector against more than one metric:

1. **Threshold-by-vibe.** Someone picks `|z| ≥ 2.0` because it
   "feels right". The detector then fires three times a week on a
   metric whose normal cycle is weekly, and the recipient learns
   within a fortnight to ignore everything from the channel.
2. **OR-merge collapse.** Two detectors at `|z| ≥ 2.0`, both
   individually reasonable, OR-merged into one alert: the merged
   stream now fires roughly twice as often as either alone (assuming
   independence; in practice usually *more*, because real metrics
   correlate). Add a third detector and the channel is noise.

The fix in both cases is the same: **calibrate thresholds against a
target alert rate, not against a target z-score.** "I want roughly
one alert per detector per fortnight" is a meaningful operational
budget. "`|z| ≥ 2.0`" is not.

This template shows how to do that calibration with three or four
weeks of historical metric data, how to combine multiple detectors
without doubling your noise, and how to wire a *back-off rule* that
silences a detector that has blown its budget two weeks running.

## What's in the box

```
alert-noise-budget/
├── README.md                       # this file
├── BUDGET.md                       # methodology: target rate → threshold table
├── bin/
│   ├── calibrate.py                # given a metric history, recommend thresholds
│   └── merge-budget.py             # given N detectors, project merged alert rate
├── prompts/
│   └── tune.md                     # strict-JSON prompt: tune one detector against budget
└── examples/
    ├── 01-single-detector-zscore/  # one metric, z-score, weekly budget = 1
    ├── 02-or-merge-two-detectors/  # cache-hit-ratio + token-volume OR-merge
    └── 03-back-off-after-budget-blown/   # detector exceeded budget 2 weeks → auto-silence
```

## When to use this template

Use it the moment you have:

- **More than one** running anomaly detector firing into the same
  channel (Slack, webhook, desktop banner, email);
- A history (≥ 3 weeks, ideally ≥ 6) of the metric(s) being scored,
  so calibration is grounded;
- A human on the other end whose attention is finite.

Do **not** use it for:

- One-off investigations ("did anything weird happen yesterday?")
  — for those, just run the detector and look. Budgeting matters
  only when alerts are recurring.
- Hard SLO breaches (e.g. "request error rate > 1%"). Those are
  threshold-by-contract, not threshold-by-budget. They get their own
  channel and they fire whenever they fire.

## Five concepts the template makes concrete

1. **Alert budget.** A target alert rate per detector, expressed as
   alerts per unit time (per day / week / fortnight). Typical
   defaults: ops dashboards 1/week per detector; experimental
   detectors 1/day until proven; SLO-style hard breaches no budget,
   they always fire.
2. **Calibration window.** The historical span you score against to
   pick a threshold. Must be long enough to contain the metric's
   natural cycle (≥ 2 cycles). For a metric with a weekly seasonal
   pattern this means ≥ 14 days; for a daily-cycle metric ≥ 2 days
   is enough but ≥ 14 is safer.
3. **Empirical-quantile threshold.** Instead of `|z| ≥ 2.0`, pick
   the threshold *t* such that, when scored against the calibration
   window, the detector would have fired exactly *budget* times.
   For a weekly budget = 1 against a 28-day window: pick the 4th
   largest absolute score across those 28 days. That's your
   threshold.
4. **OR-merge inflation factor.** Two independent detectors at
   budget *b* each, OR-merged, do **not** produce merged budget
   `2b`. They produce roughly `2b - b² / N` alerts (where N is the
   total opportunity count) — close to `2b` for small budgets, but
   *correlation between detectors makes it worse*: positively
   correlated detectors collapse toward `b` (cheap), negatively
   correlated ones expand toward `2b` (expensive). The
   `merge-budget.py` script estimates this from the joint history.
5. **Two-strikes back-off.** If a detector exceeds its budget two
   consecutive budget-windows, silence it for one full window and
   re-calibrate at the start of the next. This keeps a regime-shift
   metric (one whose underlying distribution has changed) from
   monopolizing the channel until you have time to fix it properly.

## Quickstart

```bash
# 1. Calibrate one detector against a metric history.
python3 bin/calibrate.py \
    --history examples/01-single-detector-zscore/history.csv \
    --scorer zscore \
    --window 28 \
    --budget-per-week 1
# → prints: recommended threshold = 2.41 (would have fired 4/28 days)

# 2. Project the merged alert rate of two detectors.
python3 bin/merge-budget.py \
    --history examples/02-or-merge-two-detectors/history.csv \
    --detector "ratio:zscore:2.41" \
    --detector "tokens:zscore:2.18" \
    --window 28
# → prints: projected merged rate = 6/28 (vs naive sum 8/28); correlation = +0.31

# 3. Tune via an LLM agent against a structured prompt (dry-run safe).
AGENT_CMD="" bash bin/tune.sh examples/01-single-detector-zscore/history.csv
# → prints the prompt that would be sent (no agent invoked).
```

## Decision rule (one screen)

When wiring a new detector into an existing channel:

1. **Check the channel's current load.** If the channel is already
   over its aggregate budget (sum of per-detector budgets), do
   **not** add the new detector — fix the existing ones first.
2. **Pick a per-detector budget** based on detector class:
   - SLO-style hard breach → no budget, always fires;
   - Stable production metric → 1/week;
   - New / experimental / drifting metric → 1/day for first
     fortnight, then re-evaluate;
3. **Calibrate threshold via empirical quantile** over a calibration
   window of ≥ 2 natural cycles.
4. **Project OR-merged rate** with `merge-budget.py` against existing
   detectors on the same channel. If projected merged rate exceeds
   aggregate budget, *raise* one of the per-detector thresholds
   until projection fits.
5. **Wire back-off**: track per-detector fire counts per
   budget-window; auto-silence after two consecutive over-budget
   windows; emit a one-line "muted: $detector for 1w" notice when
   silencing.

## What this template explicitly does NOT do

- Does not ship its own scheduler (use `anomaly-alert-cron`).
- Does not ship its own scorers (use
  `metric-baseline-rolling-window`).
- Does not handle hard-SLO breach alerts (those are threshold-by-
  contract, not threshold-by-budget; route them to a separate
  channel without going through this template).
- Does not handle alert *deduplication* within a single budget
  window (use `anomaly-alert-cron`'s per-day dedup; this template
  assumes "fired once per check" semantics).

## See also

- `templates/metric-baseline-rolling-window/` — the scoring layer
  (z-score, MAD, EWMA, zero-aware) that this template assumes you
  already have.
- `templates/anomaly-alert-cron/` — the scheduling + dedup +
  notifier layer that consumes the thresholds this template
  produces.
- `templates/failure-mode-catalog/` — for cataloguing what kinds of
  metric drift you've seen, which feeds back into calibration window
  choice.
