# `tool-call-cost-estimator`

Pre-flight token + dollar estimate for a planned LLM call. Pure,
deterministic, stdlib-only. The estimator does **not** issue the call
— it returns a structured estimate the orchestrator uses to decide:
**send as planned, downgrade the model, trim context, or refuse.**

Companion to:

- [`agent-cost-budget-envelope`](../agent-cost-budget-envelope/) —
  policy gate: "is *any* call from this caller currently allowed?"
- [`cost-budget-soft-fence`](../cost-budget-soft-fence/) —
  post-spend ledger: "how close to the wall did I land?"

This template fills the missing third piece: **per-call** worst-case
cost *before* you commit to the call.

## Why pre-flight, not post-hoc

A post-hoc cost ledger tells you what already happened. By then:

- The expensive call already ran — you can't un-spend.
- You can't downgrade to a cheaper model *for this attempt*.
- You can't notice a context-window blowout until the provider rejects.

A pre-flight estimate gives the orchestrator a chance to:

1. **Refuse** a single call that exceeds a per-call cost ceiling.
2. **Downgrade** to the cheapest model that fits the budget and the
   context (`cheapest_model_that_fits`).
3. **Trim** context before sending, when the prompt is the cost driver
   rather than the completion.
4. **Surface** a forecast in the agent trace so an operator can
   correlate spend forecasts with actual spend later.

## Contract

A `CallPlan` carries everything that contributes to cost:

- `model` — id used to look up `(prompt_per_1k, completion_per_1k)`.
  Unknown model **raises** `UnknownModel`. Silent "free" defaults are
  the wrong behavior for a budget gate.
- `system_prompt`, `user_prompt`, `extras: list[str]` — the prompt-side
  bytes. `extras` is for retrieved docs, tool schemas, prior turns —
  anything you'll concatenate into the request.
- `max_completion_tokens` — the **caller's own ceiling** on completion
  length. The estimate uses this as a worst case; actual spend will
  almost always be lower.

`estimate(plan)` returns prompt tokens, worst-case completion tokens,
worst-case dollar cost, and **`context_fill_ratio`** (prompt tokens
÷ model nominal context window). A 99% fill ratio is a near-certain
provider rejection; gate on it explicitly.

`gate(plan, max_cost_usd=…, max_context_fill=…)` is the all-in-one:
estimate + binary allow/deny + a human-readable reason.

`cheapest_model_that_fits(plan, candidates, …)` is the pivot point:
when a single planned model is too expensive, the orchestrator can
ask the estimator to pick the cheapest candidate that satisfies *both*
the cost ceiling and the context-fill ceiling.

### Token counter

The bundled `count_tokens` is a deterministic word-plus-char-run
heuristic — within ~10% of `cl100k_base` on English prose, fully
self-contained for a stdlib-only template. Production callers swap
it for the real tokenizer of their model family by replacing
`estimator.count_tokens`. The rest of the estimator is unchanged.

### Pricing

`DEFAULT_PRICES` ships with three placeholder tiers (`small-fast`,
`mid-balanced`, `big-smart`) so the worked example runs without
external configuration. Real deployments load prices from a file
**pinned in git** so a price change is a reviewable diff, not a silent
production change.

## Worked example output

`python3 worked_example.py` prints the following (captured verbatim
from a real run):

```
================================================================
1. Bare estimate against the planned model
================================================================
{
  "model": "mid-balanced",
  "prompt_tokens": 175,
  "completion_tokens_max": 600,
  "total_tokens_max": 775,
  "prompt_cost_usd": 0.000437,
  "completion_cost_usd_max": 0.006,
  "total_cost_usd_max": 0.006438,
  "context_fill_ratio": 0.0053
}

================================================================
2. Per-call cost gate (ceiling = $0.005)
================================================================
allow=False  reason='cost ceiling exceeded: $0.0064 > $0.0050'
estimated max cost: $0.00644

================================================================
3. Same plan, but on the expensive model
================================================================
allow=False  reason='cost ceiling exceeded: $0.0386 > $0.0050'
estimated max cost: $0.03862

================================================================
4. Cheapest model that satisfies a $0.01 ceiling
================================================================
picked: small-fast
max cost: $0.00039
prompt tokens: 175  context fill: 2.14%

================================================================
5. Context-fill gate (huge prompt, small model)
================================================================
allow=False  reason='context fill exceeded: 99.79% > 50%'
prompt tokens: 8175  fill: 99.79%
```

The five sections demonstrate, in order:

1. The estimator emits a structured forecast — every number the gate
   needs, plus the prompt/completion split for cost attribution.
2. A tight $0.005 ceiling **denies** the planned `mid-balanced` call;
   the worst-case completion is what dominates.
3. The same plan on `big-smart` denies far more loudly — useful for
   "should I escalate?" decisions where the orchestrator weighs the
   cost-to-quality tradeoff.
4. With a $0.01 ceiling, `cheapest_model_that_fits` picks `small-fast`
   — the orchestrator gets both the model id and the estimate so it
   can record the downgrade in the trace.
5. The context-fill gate fires independently of cost: even if the
   call would be cheap, an 8 175-token prompt against an 8 192-token
   window is a near-certain rejection, so the gate refuses early
   instead of letting the provider reject and burn the cost anyway.

## Files

- [`estimator.py`](estimator.py) — pure logic: `count_tokens`,
  `CallPlan`, `Estimate`, `estimate`, `gate`,
  `cheapest_model_that_fits`.
- [`worked_example.py`](worked_example.py) — runnable end-to-end
  demonstration. Output above is captured from this script.

## Operating notes

- **Worst-case, not expected-case.** The estimator multiplies by
  `max_completion_tokens`, not a learned average. Use it to refuse
  pathological plans, then track actuals with
  [`cost-budget-soft-fence`](../cost-budget-soft-fence/) to learn the
  real distribution.
- **Pin the price file.** A price change should appear in a diff and
  go through review. Loading prices from a remote endpoint at call
  time defeats the gate.
- **One call, one estimate.** This template gates a single call. For
  cumulative spend across an agent loop, layer the soft-fence on top.
