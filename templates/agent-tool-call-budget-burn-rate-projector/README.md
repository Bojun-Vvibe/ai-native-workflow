# agent-tool-call-budget-burn-rate-projector

Project remaining tool-call budget runway from a recent spend window, so the
host can throttle / hand off / downshift the model **before** an agent
hits the hard wall mid-call. Pure stdlib, deterministic, pure function
over an in-memory list — no I/O, no clocks (the `now` value is injected
for testability).

## Why this exists (vs. existing budget templates)

The catalog already has:

- `agent-step-budget-monitor` — hard wall on cost / latency budgets.
- `agent-loop-iteration-cap` — hard wall on iteration count.
- `cost-budget-soft-fence` — single-call envelope.
- `retry-budget-tracker` — retry count book-keeping.
- `token-budget-tracker` — running total of token spend.

All of those answer **"have we crossed the line?"** This template
answers **"how long until we cross it, given how we are spending right
now?"** That's the difference between an agent crashing into a wall
mid-`edit_file` and an orchestrator gracefully handing off with
`partial` and a structured "ran out of runway, here is what I got"
message.

## Why a windowed burn rate (not all-time average)?

Missions have phases. A scout phase might burn 10% of budget in 5s of
parallel reads, then sit idle for 60s while the actor thinks. All-time
average says "you have 4 hours left." Windowed says "at your current
rate you have 12 seconds left." The latter is the actionable signal.

`window_seconds` should match the dispatcher's check cadence — if the
host re-checks every 30s, a 60s window gives 2 ticks of smoothing
without lagging behind a real spike.

## Verdicts

| `verdict` | Meaning | Suggested host action |
| --- | --- | --- |
| `no_signal` | Spend list empty. | Continue; re-check after first spend event. |
| `ok` | Under soft fence. | Continue. |
| `warn` | At/over soft fence (default 0.6 of budget). | Log; consider switching to a cheaper model for next call. |
| `throttle` | At/over hard fence (default 0.85). | Refuse new non-critical tool calls; finish what's in flight. |
| `exhausted` | `spent_total >= budget`. | Hand off with `partial` envelope; do not start any new spend. |

## Edge-case rules (chosen on purpose)

- **Strict lower bound on the window.** Events at exactly `now -
  window_seconds` are *excluded* — otherwise a 30s window would
  double-count an event sitting on the boundary across two consecutive
  ticks.
- **`eta_seconds` is `None`, not infinity, when burn rate is zero** —
  JSON-serializable and unambiguous.
- **Negative `remaining` clamps `eta_seconds` to `0.0`** (you are
  already over).
- **Out-of-order timestamps raise `BudgetInputError`** — silently
  re-sorting would mask an upstream instrumentation bug.
- **Future-dated spend events raise** — clock skew or a caller bug;
  failing loud is correct.

## Usage

```bash
python3 project.py example_input.json
```

Input is a `{"cases": [{"name": ..., "budget": ..., "now": ...,
"window_seconds": ..., "spend": [[ts, cost], ...]}, ...]}` document so
one run can exercise multiple scenarios. `BudgetInputError` is caught
per-case and reported as `{"error": "..."}` so a malformed case does
not abort the whole batch.

## Worked example

`example_input.json` covers seven scenarios. Verbatim output captured in
`example_output.txt`:

```json
[
  {
    "name": "01_no_signal_empty",
    "result": {
      "burn_rate_per_sec": 0.0,
      "eta_seconds": null,
      "fraction_spent": 0.0,
      "remaining": 5.0,
      "spent_total": 0.0,
      "verdict": "no_signal",
      "window_seconds": 60.0,
      "window_spend": 0.0
    }
  },
  {
    "name": "02_ok_steady_low_burn",
    "result": {
      "burn_rate_per_sec": 0.001667,
      "eta_seconds": 2880.0,
      "fraction_spent": 0.04,
      "remaining": 4.8,
      "spent_total": 0.2,
      "verdict": "ok",
      "window_seconds": 60.0,
      "window_spend": 0.1
    }
  },
  {
    "name": "03_warn_over_soft_fence",
    "result": {
      "burn_rate_per_sec": 0.016667,
      "eta_seconds": 108.0,
      "fraction_spent": 0.64,
      "remaining": 1.8,
      "spent_total": 3.2,
      "verdict": "warn",
      "window_seconds": 60.0,
      "window_spend": 1.0
    }
  },
  {
    "name": "04_throttle_short_runway",
    "result": {
      "burn_rate_per_sec": 0.046667,
      "eta_seconds": 12.857,
      "fraction_spent": 0.88,
      "remaining": 0.6,
      "spent_total": 4.4,
      "verdict": "throttle",
      "window_seconds": 30.0,
      "window_spend": 1.4
    }
  },
  {
    "name": "05_exhausted_over_budget",
    "result": {
      "burn_rate_per_sec": 0.013333,
      "eta_seconds": 0.0,
      "fraction_spent": 1.06,
      "remaining": -0.3,
      "spent_total": 5.3,
      "verdict": "exhausted",
      "window_seconds": 60.0,
      "window_spend": 0.8
    }
  },
  {
    "name": "06_zero_burn_idle_phase",
    "result": {
      "burn_rate_per_sec": 0.0,
      "eta_seconds": null,
      "fraction_spent": 0.4,
      "remaining": 3.0,
      "spent_total": 2.0,
      "verdict": "ok",
      "window_seconds": 60.0,
      "window_spend": 0.0
    }
  },
  {
    "error": "spend timestamps must be non-decreasing; spend[1].ts=940.0 < previous 950.0",
    "name": "07_invalid_out_of_order"
  }
]
```

What each case demonstrates:

- **01**: empty history → `no_signal`, not a false `ok`.
- **02**: low steady burn well under the soft fence → `ok` with a
  comfortably long ETA.
- **03**: one big historical spend pushed `fraction_spent` to 0.64,
  past the 0.6 soft fence → `warn`. Window burn projects 108s of
  runway.
- **04**: `fraction_spent=0.88` past the 0.85 hard fence → `throttle`;
  a 30s window with 1.4 spend gives a stark 12.857s ETA.
- **05**: spent_total > budget → `exhausted`; eta clamped to `0.0`,
  `remaining` reported as negative so the host can see how far over.
- **06**: idle phase — old spend counts toward total but window is
  empty → `burn_rate_per_sec=0.0` and `eta_seconds=null`, *not* a
  divide-by-zero or fake-infinity.
- **07**: out-of-order timestamps caught and reported as a structured
  `error`, the rest of the batch still runs.

Run end-to-end:

```bash
$ python3 project.py example_input.json
# → exit 0; 7 case results printed
```

## Composes with

- `agent-step-budget-monitor` — this template fires `warn` / `throttle`
  *before* the monitor's hard wall, giving the agent time to degrade
  gracefully.
- `cost-budget-soft-fence` — per-call envelope; this template is the
  mission-level rollup.
- `agent-handoff-protocol` — when verdict crosses to `throttle` or
  `exhausted`, hand off with `partial` (still useful) or
  `unrecoverable` (had to abort).
- `model-fallback-ladder` — verdict `warn` is the natural trigger to
  step one rung down the ladder for the next call.
