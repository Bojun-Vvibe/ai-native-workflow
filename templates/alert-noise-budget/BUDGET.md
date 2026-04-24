# BUDGET.md — Methodology

How to translate "I want roughly N alerts per week from this
detector" into an actual numerical threshold, and what to do when
multiple detectors share a channel.

## 1. Pick a budget per detector class

| Detector class                                 | Budget per window | Rationale                                                                   |
| ---------------------------------------------- | ----------------- | --------------------------------------------------------------------------- |
| Hard SLO breach (e.g. error rate > contract)   | unbounded         | Always fires; route to a separate channel; not the subject of this template. |
| Stable production metric, mature detector      | 1 / week          | High signal-to-noise floor; recipient pays attention when it fires.          |
| New / experimental detector, first fortnight   | 1 / day           | You haven't yet seen its real false-positive rate. Loosen later.            |
| Drifting metric, pre-fix, known-noisy          | 0 / week (mute)   | Auto-silenced under the two-strikes back-off rule below.                    |

The point is that "budget" is *per detector*, not per channel. The
channel's aggregate budget is the **sum** of the per-detector
budgets, and you keep the merged stream below that sum by
calibrating individual thresholds and accepting OR-merge inflation
(see §3).

## 2. Calibrate threshold by empirical quantile

Given a calibration window of length `W` days and a target budget of
`b` alerts per `W` days for one detector:

1. Score every day in the window. Get an array of `W` absolute
   scores (z, MAD, EWMA — whichever scorer the detector uses).
2. Sort descending.
3. Pick the `b`-th score (1-indexed) as the threshold. The detector
   *would have fired* exactly `b` times across the calibration
   window at that threshold — by construction.

This guarantees the historical alert rate matches the budget
exactly. It does **not** guarantee the future rate will, because
metric distributions drift. The two-strikes back-off rule (§4)
catches drift; the calibration only sets the starting point.

### Worked example

Calibration window = 28 days; weekly budget = 1 alert; budget across
window = 4 alerts (W / 7 × budget).

Scores sorted descending: `[3.21, 2.87, 2.51, 2.41, 2.18, 2.05,
1.92, ...]`.

Threshold = 2.41 (the 4th value). At this threshold the detector
would have fired on exactly 4 of the 28 days.

**Sanity check:** if the 4th score is ≤ 1.5, the metric is too
quiet for the requested budget — the detector will fire only on
genuine outliers, which is fine, but be aware that it may go
*weeks* without firing. If the 4th score is ≥ 4.0, the metric is
spikier than expected and you may want to widen the calibration
window or switch scorer (z-score is bad on spiky metrics; try MAD).

## 3. OR-merge inflation between detectors

Two independent detectors at budget `b` each, OR-merged into one
alert stream, produce a merged rate of:

```
merged = b_1 + b_2 - P(both fire same day)
```

where `P(both fire same day)` depends on the joint distribution of
the two scoring streams. Three regimes:

- **Independent detectors** (correlation ≈ 0): `P(both) ≈ b_1 × b_2
  / W`. For small budgets this is tiny, so `merged ≈ b_1 + b_2`.
- **Positively correlated detectors** (e.g. cache-hit-ratio drop and
  token-volume spike both caused by the same upstream incident):
  they tend to fire on the same days; `P(both)` is larger; `merged`
  collapses *toward* `max(b_1, b_2)`. Cheap merge.
- **Negatively correlated detectors** (rare; happens when one
  metric absorbs traffic the other loses): they fire on
  *different* days; `P(both) ≈ 0`; `merged ≈ b_1 + b_2`. Worst
  case.

The script `bin/merge-budget.py` estimates the joint behaviour
empirically from a multi-column history. Use it to decide whether
adding a new detector to an existing channel will blow the
aggregate budget.

### Operational rule

If projected `merged` exceeds the channel's aggregate budget by more
than 25%, **raise the threshold of the noisier detector** (the one
with the higher individual budget) until projection fits. Do *not*
raise both equally — that throws away signal symmetrically when only
one detector is the actual offender.

## 4. Two-strikes back-off

A detector that exceeds its budget in two **consecutive** budget
windows is auto-silenced for one full window, and re-calibrated at
the start of the next.

Why two strikes, not one: a single over-budget window is consistent
with normal statistical variance — at budget 1/week, a Poisson
process will produce ≥ 2 alerts in a week roughly 26% of the time
just by chance. Two consecutive over-budget windows is much rarer
(≈ 7%) and is a real signal that the underlying distribution has
shifted.

Why one window of silence, not permanent: regime shifts are usually
transient (incident, deploy, traffic pattern change). Re-calibrating
after one window gives the detector a chance to come back online
under the new distribution. If it blows budget again, silence again
— but at this point a human should be looking at *why* the metric
keeps drifting, not at the detector.

### What the silence message should say

When silencing, emit one line into the same channel:

```
muted: cache-hit-ratio-zscore for 1w (over-budget 2 consecutive weeks; will re-calibrate 2026-05-01)
```

That's enough for the recipient to understand the channel went
quiet on purpose, and to know when it will come back.

## 5. Anti-patterns to avoid

- **Threshold-by-vibe.** "`|z| ≥ 2.0` because that's the textbook
  number." Textbook numbers come from textbook distributions; your
  metric does not have a textbook distribution.
- **Threshold-by-current-fire-rate.** "It's firing too much, raise
  the threshold." Yes, but raise it *to a number*, derived from a
  budget, not to "wherever stops it firing for now". Otherwise
  you'll be re-tuning monthly.
- **Per-channel global threshold.** "All detectors on this channel
  fire at `|z| ≥ 2.5`." This conflates detector-class budgets;
  experimental and mature detectors should not share a threshold
  number.
- **Silencing without a re-calibration date.** Once silenced, the
  detector should have a known re-evaluation moment. "Muted until
  someone notices" is how silenced-and-forgotten detectors happen.
- **Adding a detector without projecting OR-merge inflation.** This
  is how channels degrade — one detector at a time, each
  individually fine, aggregate intolerable.
