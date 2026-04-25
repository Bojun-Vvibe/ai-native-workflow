# latency-aware-model-picker

Pure, stdlib-only picker that selects one of N model rungs per request
based on a rolling **p95-latency** + **failure-rate** signal, not on
cost alone. Returns `Pick(rung_id, reason, ...)` or `Defer(reason,
suggested_wait_s)` so the orchestrator never has to silently retry
against a rung that just blew up its tail.

Sibling of `weighted-model-router` (probabilistic, weight-stable
selection) and `model-fallback-ladder` (sequential climb on failure).
This template is the *health-aware* counterpart: it answers "which rung
*should* I try first this second" given recent observed behaviour, not
"how should the long-run distribution look" or "what's the next rung
after a known failure".

## Why it matters

Cost-only routing picks the cheapest healthy rung. The trap: under load
or during a vendor incident, the cheapest rung's p95 can quintuple while
its mean stays fine, and your agent UX dies in the tail. Conversely,
naive "pick the lowest measured latency" routing has a selection bias
problem — a rung that's been failing every call for a minute looks
"fast" because failures return quickly. This picker uses both signals
(p95 + failure_rate), evaluates failure_rate first as a hard gate, and
deliberately avoids picking a fast-but-broken rung.

The picker is deliberately stateless. The caller owns the per-rung
`Stats` window and feeds it back in next time, which means:

- Multi-process callers can persist Stats however they like (in-memory,
  Redis, shared file). The picker doesn't care.
- Tests are byte-deterministic — no clocks, no global RNG.
- The picker can be replayed against historical Stats snapshots to
  audit a routing decision.

## When to use it

- Multi-rung deployments where a per-vendor incident is realistic
  (rate-limit storms, regional brownouts, cold-cache spikes after a
  deploy).
- Latency-sensitive agent UX where the user feels the p95, not the mean.
- A/B-style traffic-shifting that should auto-pause a rung when it
  degrades, without a human paging the on-call.

## When NOT to use it

- Single-rung deployments — there's nothing to pick.
- You need *deterministic* per-key routing for an experiment (use
  `weighted-model-router` instead — its HRW hash gives you stable
  per-key affinity which a health-aware picker would override).
- You need failover *during* a single call after a partial failure (use
  `model-fallback-ladder` — that template's `call_fn` per-rung trial is
  the right shape for in-flight failover).

## Contract

`pick(rungs, stats_by_rung, policy) -> Pick | Defer`

- `rungs`: an ordered iterable of `Rung(rung_id, cost_per_call_usd)`.
  Caller-preferred order is the final tiebreak — declared order matters.
- `stats_by_rung`: `dict[rung_id -> Stats]`. Missing rung_ids are
  treated as cold (no observations).
- `policy`: `LatencyPolicy(p95_budget_s, max_failure_rate=0.20,
  min_observations=5, cold_defer_s=1.0)`.

Decision order (deliberately fixed):

1. For each rung with `n >= min_observations`:
   - **Failure-rate gate first.** If `failure_rate > max_failure_rate`,
     the rung is unhealthy regardless of how fast it returns failures.
   - **Then p95 budget.** If `p95 > p95_budget_s`, the rung is over
     budget.
2. From the eligible (= passed both gates) set, pick by tiebreak:
   `(lower p95, lower cost, declared order)`.
3. If the eligible set is empty but at least one rung is **cold**
   (`n < min_observations`), sample the first cold rung in declared
   order. A cold rung is better than no rung — without sampling, a
   newly-deployed rung never accumulates observations.
4. If everything has data and everything is unhealthy, return `Defer`
   with `suggested_wait_s = min(p95 of unhealthy rungs)` so the caller
   sleeps roughly one request worth of time before re-checking.

p95 is computed by **nearest-rank** on the rolling window
(`ceil(0.95 * N) - 1`), not interpolation, because the window is small
and interpolation hides single-call tail spikes that matter.

## Files

- `picker.py` — `Stats`, `Rung`, `LatencyPolicy`, `Pick`, `Defer`,
  `pick()`. ~190 lines, stdlib-only.
- `worked_example.py` — five realistic scenarios that together verify
  every branch of the decision tree.

## Sample run output

```
======================================================================
Case 1: steady-state — all rungs healthy
======================================================================
p95s: {'fast-cheap': 0.34, 'mid-balanced': 0.55, 'big-smart': 1.31}
verdict:
    verdict = 'pick'
    rung_id = 'fast-cheap'
    reason = 'within_budget'
    p95_s = 0.34
    failure_rate = 0.0
    n = 12

======================================================================
Case 2: mid-rung tail blowup — picker should skip mid
======================================================================
p95s: {'fast-cheap': 4.0, 'mid-balanced': 13.0, 'big-smart': 1.31}
verdict:
    verdict = 'pick'
    rung_id = 'big-smart'
    reason = 'within_budget'
    p95_s = 1.31
    failure_rate = 0.0
    n = 12

======================================================================
Case 3: all rungs degraded — should defer
======================================================================
p95s: {'fast-cheap': 5.0, 'mid-balanced': 4.0, 'big-smart': 0.5}
failure_rates: {'fast-cheap': 0.0, 'mid-balanced': 0.0, 'big-smart': 0.583}
verdict:
    verdict = 'defer'
    reason = 'all_rungs_unhealthy'
    suggested_wait_s = 0.5

======================================================================
Case 4: cold rung available — sample it instead of deferring
======================================================================
p95s: {'fast-cheap': 5.0, 'mid-balanced': 4.0} (big-smart=COLD)
verdict:
    verdict = 'pick'
    rung_id = 'big-smart'
    reason = 'cold_rung_sampled'
    p95_s = None
    failure_rate = 0.0
    n = 0

======================================================================
Case 5: fast-but-broken — failure rate beats raw latency
======================================================================
p95s: {'fast-cheap': 0.05, 'mid-balanced': 0.4, 'big-smart': 1.2}
failure_rates: {'fast-cheap': 0.583, 'mid-balanced': 0.0, 'big-smart': 0.0}
verdict:
    verdict = 'pick'
    rung_id = 'mid-balanced'
    reason = 'within_budget'
    p95_s = 0.4
    failure_rate = 0.0
    n = 12
```

The five cases together verify five distinct invariants:

1. **Steady-state**: lowest-p95 rung wins (which is also the cheapest
   here — both signals agree).
2. **Tail blowup**: the mid rung's p95 jumped to 13s; picker skips it
   for big-smart, even though big-smart costs 6× more, because
   big-smart is the only other rung inside the 2s budget.
3. **All unhealthy**: every rung either over-budget or over-failure-
   rate; picker returns `Defer` with `suggested_wait_s=0.5` (the
   fastest unhealthy rung's p95) so the caller backs off
   intelligently.
4. **Cold rung fallback**: the third rung has zero data; picker
   samples it instead of deferring — proves a freshly-deployed rung
   accumulates the observations it needs to ever become eligible.
5. **Fast-but-broken**: fast-cheap returns in 50ms but fails 58% of
   calls; picker correctly rejects it on failure-rate grounds and
   picks mid-balanced (the slower-but-reliable rung) — proves the
   fail-rate gate runs *before* the latency tiebreak.

## Composes with

- `weighted-model-router` — call this picker to reduce the candidate
  set to the *healthy* rungs first; pass the survivors as the router's
  backend list. You get health-aware *and* per-key-stable routing.
- `model-fallback-ladder` — when this picker returns `Pick`, that's the
  ladder's *first* rung. The ladder's existing climb logic handles the
  in-flight failover cleanly.
- `tool-call-circuit-breaker` — feed `Stats.observe(latency, ok)` from
  the breaker's per-call instrument; the breaker's open/closed state
  and this picker's failure-rate gate are independent signals you want
  *both* of (breaker = trip-hard; picker = prefer-elsewhere).
- `agent-decision-log-format` — log every `Pick` and `Defer` with
  `reason` so a 10-minute incident leaves a queryable record of which
  rung was chosen and why at each minute.
- `agent-cost-budget-envelope` — budget envelope decides *whether* a
  call is allowed; this picker decides *which rung* serves an
  already-allowed call. Stack them.
