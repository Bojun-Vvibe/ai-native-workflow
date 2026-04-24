# cost-budget-soft-fence

Running per-period token-cost ledger with **staged warn rungs** at 60 / 85 /
95 % of budget *before* the hard 100 % stop, plus **refundable spends** so a
rolled-back tool call gives its dollars back (and re-arms the warn rungs it
crossed, so a refund-then-respend pattern doesn't silently mask the second
crossing).

## Companion to `agent-cost-budget-envelope`

`agent-cost-budget-envelope` answers *"can the **next** call afford to
proceed?"* — a pre-flight gate over a policy. **This** template answers
*"how close to the wall am I right now, and where did I land relative to
the warn rungs?"* — a post-spend ledger that tells the orchestrator when to
slow down before the gate slams shut.

Use both. Envelope decides; fence accumulates and warns.

## Why staged warns matter

A pure hard-cap budget gives you exactly one signal — the deny — at which
point you've already pushed up against the wall and have nowhere to land.
60 / 85 / 95 % gives the orchestrator three structurally distinct moments
to choose a response:

- **60 %** — informational. "We've burned more than half. Is the mission
  scope still sized right?"
- **85 %** — operational. "Stop launching new fan-out branches; finish
  the in-flight ones."
- **95 %** — terminal. "Wrap up the current step and exit cleanly; do not
  start the next one."
- **100 %** — `hard_stop`. The spend is rejected and not appended to the
  ledger. The caller must rollback / downsize / raise budget.

Each rung warns **exactly once** per budget period. A spend that leaps
multiple rungs at once (e.g. 50 % → 90 %) emits one `warn` for the highest
rung crossed *and* marks the lower skipped rungs as already-warned, so a
later spend cannot double-warn for them.

## Refunds and rung re-arming

A tool call that gets rolled back (transaction failed, idempotency dedup
match, agent loop detected partial failure) issues `refund(call_id)`:

- The original committed amount is subtracted from the running total.
- Any warn rung the running total has now dropped back below is re-armed,
  so a genuine subsequent crossing warns again.
- Idempotent: refunding the same `call_id` twice returns
  `status="already_refunded"` and does not double-credit.
- Refunding an unknown id returns `status="unknown"` — never crashes the
  ledger.

Without rung re-arming, a refund-then-respend flow would silently mask the
second crossing — exactly the case where you most want to be warned, since
it usually indicates a retry storm.

## Files

- `fence.py` — stdlib-only reference engine: `Ledger`, `Spend`, `Verdict`,
  with `to_dict` / `from_dict` for JSON persistence between processes.
- `examples/01_warn_then_hard_stop.py` — staged warns and a hard stop.
- `examples/02_refund_rearms.py` — refund re-arms a rung; double-refund and
  unknown-id are handled.

## Worked example 1 — staged warns then a hard stop

Budget = $1.00, default rungs = (0.60, 0.85, 0.95).

```
$ python3 examples/01_warn_then_hard_stop.py
charge c1 $0.20 (ok, no rung yet):
  {"fraction_after": 0.2, "headroom_usd": 0.8, "next_rung": null, "reason": null, "rung": null, "spent_after_usd": 0.2, "status": "ok"}
charge c2 $0.30 (lands at 0.50, still no warn):
  {"fraction_after": 0.5, "headroom_usd": 0.5, "next_rung": null, "reason": null, "rung": null, "spent_after_usd": 0.5, "status": "ok"}
charge c3 $0.15 (lands at 0.65 — crosses 60% rung):
  {"fraction_after": 0.65, "headroom_usd": 0.35, "next_rung": 0.85, "reason": null, "rung": 0.6, "spent_after_usd": 0.65, "status": "warn"}
charge c4 $0.05 (lands at 0.70 — between rungs, ok):
  {"fraction_after": 0.7, "headroom_usd": 0.3, "next_rung": null, "reason": null, "rung": null, "spent_after_usd": 0.7, "status": "ok"}
charge c5 $0.20 (lands at 0.90 — crosses 85%):
  {"fraction_after": 0.9, "headroom_usd": 0.1, "next_rung": 0.95, "reason": null, "rung": 0.85, "spent_after_usd": 0.9, "status": "warn"}
charge c6 $0.06 (lands at 0.96 — crosses 95%):
  {"fraction_after": 0.96, "headroom_usd": 0.04, "next_rung": null, "reason": null, "rung": 0.95, "spent_after_usd": 0.96, "status": "warn"}
charge c7 $0.10 (would push to 1.06 — hard_stop, REJECTED):
  {"fraction_after": 0.96, "headroom_usd": 0.04, "next_rung": null, "reason": "would exceed budget: spend 0.100000 + committed 0.960000 > budget 1.000000", "rung": null, "spent_after_usd": 0.96, "status": "hard_stop"}
charge c8 $0.04 (exactly fills budget to 1.00 — ok (no rung above 95% to cross)):
  {"fraction_after": 1.0, "headroom_usd": -0.0, "next_rung": null, "reason": null, "rung": null, "spent_after_usd": 1.0, "status": "ok"}

final ledger:
{
  "budget_usd": 1.0,
  "committed": {
    "c1": 0.2,
    "c2": 0.3,
    "c3": 0.15,
    "c4": 0.05,
    "c5": 0.2,
    "c6": 0.06,
    "c8": 0.04
  },
  "refunded": [],
  "spent_usd": 1.0,
  "warn_rungs": [0.6, 0.85, 0.95],
  "warned_rungs": [0.6, 0.85, 0.95]
}
```

Each rung warns exactly once. `c7` is rejected (would land at 1.06) — it's
not in the final `committed` map and the running total stays at 0.96 until
`c8` lands it cleanly at exactly 1.00.

## Worked example 2 — refund re-arms a rung; idempotent double-refund

```
$ python3 examples/02_refund_rearms.py
step 1 — spend up to 0.92:
  charge a $0.40 -> {"fraction_after": 0.4, "headroom_usd": 0.6, "next_rung": null, "reason": null, "rung": null, "spent_after_usd": 0.4, "status": "ok"}
  charge b $0.22 -> {"fraction_after": 0.62, "headroom_usd": 0.38, "next_rung": 0.85, "reason": null, "rung": 0.6, "spent_after_usd": 0.62, "status": "warn"}
  charge c $0.30 -> {"fraction_after": 0.92, "headroom_usd": 0.08, "next_rung": 0.95, "reason": null, "rung": 0.85, "spent_after_usd": 0.92, "status": "warn"}

step 2 — refund call 'c' (the one that crossed 85%):
  {"amount_usd": 0.3, "call_id": "c", "fraction_after": 0.62, "rearmed_rungs": [0.85], "spent_after_usd": 0.62, "status": "refunded"}

step 3 — new spend climbs back above 0.85:
  {"fraction_after": 0.87, "headroom_usd": 0.13, "next_rung": 0.95, "reason": null, "rung": 0.85, "spent_after_usd": 0.87, "status": "warn"}

step 4 — double-refund same call_id is idempotent:
  {"call_id": "c", "spent_after_usd": 0.87, "status": "already_refunded"}

step 5 — refunding an unknown call_id:
  {"call_id": "does-not-exist", "status": "unknown"}

final ledger:
{
  "budget_usd": 1.0,
  "committed": {"a": 0.4, "b": 0.22, "d": 0.25},
  "refunded": ["c"],
  "spent_usd": 0.87,
  "warn_rungs": [0.6, 0.85, 0.95],
  "warned_rungs": [0.6, 0.85]
}
```

Refunding `c` drops the total from 0.92 to 0.62 and re-arms the 0.85 rung
(noted in `rearmed_rungs`). The next genuine crossing of 0.85 (via spend
`d`) re-warns. Double-refund and unknown-id calls return structured status
without mutating the ledger.

## Integration sketch

```python
from fence import Ledger, Spend

led = Ledger.from_dict(load_json("ledger.json"))  # or fresh
verdict = led.charge(Spend(call_id=trace_span_id, amount_usd=cost))
if verdict.status == "hard_stop":
    rollback_and_raise()
elif verdict.status == "warn":
    if verdict.rung >= 0.85:
        stop_launching_new_branches()
    if verdict.rung >= 0.95:
        finish_current_step_and_exit()
save_json("ledger.json", led.to_dict())

# On rollback:
led.refund(call_id=trace_span_id)
save_json("ledger.json", led.to_dict())
```

## When NOT to use

- Pre-flight admission control on the *next* call — that's the job of
  `agent-cost-budget-envelope`. This template only knows about already-
  committed spends.
- True multi-process concurrent ledgers — the in-memory state is single-
  writer. For multi-writer use a database with a unique constraint on
  `call_id` and re-derive `spent_usd` on demand.
- Token-count budgets where prices change retroactively — use
  `token-budget-tracker`'s pinnable `prices.json` so old logs re-cost.

## Composes with

- `agent-cost-budget-envelope` — envelope is the pre-flight gate; this is
  the post-spend ledger. The fence's `headroom_usd` is exactly the value
  the envelope's per-session check uses on the next call.
- `token-budget-tracker` — feed the per-call cost into both: tracker for
  long-term reporting, fence for in-mission warnings.
- `tool-call-trace-id-propagator` — use the per-call `span_id` as the
  fence `call_id`. Refund-on-rollback then ties cleanly to the trace tree.
- `partial-failure-aggregator` — when an aggregated verdict is
  `quorum_failed → abort`, refund every successful sub-call's spend so the
  rolled-back fan-out doesn't permanently consume budget.
