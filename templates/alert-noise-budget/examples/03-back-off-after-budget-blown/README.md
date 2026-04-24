# Example 03 — two-strikes back-off after a regime shift

A detector tuned against a stable two-week baseline encounters a
regime shift in week 3: the underlying metric mean drifts up and
its variance roughly triples. The detector's frozen baseline can no
longer represent the new regime — it fires on most days. The
two-strikes rule catches this and silences the detector after two
consecutive over-budget weeks.

This is the realistic case for any detector with a *frozen*
baseline (most production detectors). Rolling-window detectors
re-baseline continuously and don't show this failure mode in the
same way, but they have their own problem: they silently absorb the
new regime and stop alerting on it at all.

## Inputs

- `history.csv` — 28 days. Days 0–13: stable around mean=500, sd=30.
  Days 14–27: regime shift to mean=580, sd=75.
- `fires.csv` — pre-computed per-day fire log of a frozen-baseline
  detector tuned to budget 1/week against weeks 1–2.

## Step 1 — see the threshold the detector was tuned to

```bash
python3 ../../bin/calibrate.py --history history.csv \
    --metric value --scorer zscore --window 14 --budget-per-week 1
```

(Calibrated against the **first** 14 days. Threshold ≈ 1.6 in
z-units of the baseline distribution.)

## Step 2 — apply the two-strikes back-off rule

```bash
python3 ../../bin/back-off.py --fires fires.csv --budget-per-week 1
```

Expected output:

```
budget: 1 fires/week (over-budget if fires > 1)

  week start      fires  state         action
  ---- ---------- -----  ------------  ---------------------------
     0 2026-03-13     0  ok            
     1 2026-03-20     2  warn          first strike — investigate but keep firing
     2 2026-03-27     6  mute          two strikes — mute for week 3
     3 2026-04-03     5  recalibrate   mute window expired; re-calibrate threshold from current history
```

## Reading the output

- **Week 0:** baseline period; 0 fires (calibration was tuned to ≤
  budget against this period). Status `ok`.
- **Week 1:** baseline period; 2 fires (slightly over-budget by
  chance — Poisson variance). Status `warn`. The rule does not mute
  on a single over-budget week, because random variation alone
  produces ~26% over-budget weeks at budget = 1.
- **Week 2:** regime shift hits. 6 fires against budget 1. Status
  `mute`. Detector is silenced for week 3.
- **Week 3:** mute window expires; status `recalibrate`. The
  operator (or an automated job) should now compute a new threshold
  from the current 14-day history (which now includes the new
  regime) and re-deploy.

## What this teaches

- **Variance alone produces over-budget weeks.** The first strike
  is not a problem to fix; it's expected. Muting on a single
  over-budget week throws away signal unnecessarily.
- **Two strikes is a strong signal.** At budget 1/week, two
  consecutive over-budget weeks happens by chance ~7% of the time.
  In practice when you see it, the metric has actually shifted.
- **Mute, don't delete.** The mute is one week, not permanent. The
  detector comes back online after re-calibration. If the metric
  has truly entered a new regime, the new calibration window will
  capture that and the detector will be useful again. If the regime
  shift was transient (incident resolved, deploy reverted), the new
  calibration may even produce a similar threshold.
- **The silence message is for the recipient.** When you mute, emit
  one line into the channel saying `muted: <detector> for 1w
  (re-calibrate <date>)`. Otherwise the recipient won't know why
  the channel went quiet and may assume the detector is still firing
  but the alerts are getting lost — which produces *more* anxiety
  than the noise did.

## What this does NOT teach

This example uses a frozen-baseline detector to make the failure
mode visible. A rolling-window detector (z-score against a moving
14-day window) would NOT exhibit this failure mode the same way:
the new regime would be absorbed into the baseline within 14 days,
and the detector would stop firing on the regime shift entirely —
which is a different (often worse) failure: the detector is silent
because it has accepted the new regime as normal, not because it's
muted. That failure is harder to detect and is out of scope for
this template; see `failure-mode-catalog/` for cataloguing it.
