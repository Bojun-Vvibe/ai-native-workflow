# Example 02 — OR-merge two detectors with positive correlation

Two detectors against a synthetic 28-day history of cache-hit ratio
and daily token volume. Two genuine incidents in the window cause
**both** metrics to deflect on the same day (ratio drops, tokens
spike). One additional ratio-only blip happens mid-window.

Each detector is individually calibrated to a budget of 1/week. The
question this example answers: what is the *combined* alert rate
when both detectors share a channel?

## Inputs

- `history.csv` — 28 days, columns `date,ratio,tokens`. Ratio
  ~ 0.65 ± 0.04, tokens ~ 5M ± 600k. Two correlated incidents
  (days 10, 22) and one ratio-only blip (day 17).
- Both detectors use `zscore`. Budget: 1/week per detector → 2/week
  aggregate naively, but in practice less because they correlate.

## Step 1 — calibrate each detector individually

```bash
python3 ../../bin/calibrate.py --history history.csv --metric ratio  --scorer zscore --window 28 --budget-per-week 1
# → recommended threshold (|score| >=): 1.074
python3 ../../bin/calibrate.py --history history.csv --metric tokens --scorer zscore --window 28 --budget-per-week 1
# → recommended threshold (|score| >=): 1.359
```

## Step 2 — project the OR-merged rate

```bash
python3 ../../bin/merge-budget.py --history history.csv --window 28 \
    --detector "ratio:zscore:1.074" \
    --detector "tokens:zscore:1.359"
```

Expected output:

```
window: 28 days, 2 detectors

  ratio                zscore threshold=1.074  fired 3/28 days
  tokens               zscore threshold=1.359  fired 3/28 days

  naive sum of fires:      6/28 days  (what a noise-blind operator expects)
  actual OR-merged fires:  4/28 days  (what the channel actually receives)
  collapsed 2 fires (positive correlation between detectors — cheap merge)

  pairwise correlation of fire-day indicators:
    ratio           <-> tokens           r = +0.63
```

## What this teaches

- **Naive expectation:** "two detectors, each at 1/week, → 2/week
  aggregate." The naive sum of 6/28 ≈ 1.5/week (close to that).
- **Reality:** OR-merge collapsed to 4/28 ≈ 1/week because the two
  detectors *fire on the same days*. Their fire-day indicators
  correlate at r = +0.63 — high enough that adding the second
  detector adds almost no marginal noise.
- **Operational implication:** if you've already accepted 1/week of
  noise from one of these detectors, the second one is essentially
  free. You can wire it in without raising the channel's aggregate
  alert load.
- **The opposite case** would be two detectors with r ≈ 0 or r < 0
  — they'd fire on disjoint days and the merged rate would be
  closer to the naive sum 6/28 ≈ 2/week. In that case you'd raise
  one of the per-detector thresholds to fit the channel budget,
  picking the detector with the higher individual budget (more
  noise to give back).

## Why this matters generally

Many real-world detector pairs are positively correlated because the
underlying *incident* is what causes both metrics to deflect (a
backend slowdown both raises latency and drops cache-hit ratio; a
deploy both spikes errors and changes token usage). For these pairs
OR-merge is cheap and you should just do it.

A small minority of pairs are negatively correlated — typically
when one metric absorbs traffic the other loses (e.g. cached
requests vs uncached requests). These require care: OR-merging them
adds full noise of both, and you may want separate channels.

The whole point of running `merge-budget.py` *before* wiring a new
detector is to find out which case you're in, before the channel
goes into noise collapse and the recipient mutes it.
