# Template: agent-cost-budget-envelope

A small budget-enforcement envelope that wraps every model call with
three hard caps — **per-call**, **per-session**, and **per-day** —
plus a **graceful-degrade tier** the caller can opt into and a
**kill switch** for the case where degrade is not safe. The envelope
is a single dataclass + a pre-call check function + a post-call
ledger update; the policy lives in a JSON file that an operator can
edit without touching code.

This template is the per-call/per-session counterpart to
`token-budget-tracker` (which records spend after the fact for
reporting) and `alert-noise-budget` (which calibrates an alert rate
budget). Those answer "how much did we spend?" and "how many alerts
should we expect?". This one answers **"is this next call allowed
to happen at all?"** — and if yes, **"at what tier?"**.

## Why this exists

Three failure modes that show up the moment an agent loop is
running on autopilot:

1. **The runaway session.** A repair loop, a retry envelope, and a
   tool-result-of-a-tool-result all compose. One mission spends
   $40 in 90 seconds because nothing on the call path knew the
   per-session budget. Per-call alone is not enough.
2. **The slow drip.** Each call is small (≤ $0.05). The agent
   makes 4,000 of them across the day because nothing checked the
   per-day rollup. Per-session alone is not enough either.
3. **Hard-fail vs degrade ambiguity.** When budget trips,
   half the system wants `raise BudgetExceeded`, the other half
   wants "fall back to a cheaper model and a shorter context."
   Deciding ad-hoc per call site is how you ship inconsistencies.

The envelope makes the decision deterministic: each cap has a
declared `on_trip` policy of `degrade` or `kill`, and a
`degrade_to` tier that names the cheaper substitute. The agent
loop calls `check()` once before each model call and gets back one
of `allow`, `allow_degraded`, or `deny` plus a structured reason.

## When to use

- You run an agent loop where one mission can issue many model
  calls and you cannot trust that each individual call site
  remembered to check.
- You want a single operator-visible knob (`policy.json`) for "how
  much can this agent spend per session today" without redeploying
  code.
- You want a kill switch that an on-call can flip to `0.0` without
  touching the agent loop.

## When NOT to use

- You only have one model call per request (web request → one
  completion). A simple per-request middleware is enough.
- You need provider-side enforcement (refuses at the API). This
  template is *host-side* — it cannot stop a misconfigured caller
  from bypassing the envelope. Pair with provider-side quotas if
  the threat model requires it.
- You are doing fine-grained cost attribution (per-tenant, per-tool,
  per-phase). Use `token-budget-tracker` for that; this envelope
  only answers "allow / degrade / deny" against three rollups.

## What's in the box

| File | What it does |
|---|---|
| `ENVELOPE.md` | The spec: policy schema, three caps, degrade tier rules, kill-switch semantics, ledger schema, anti-patterns |
| `bin/budget_envelope.py` | Reference engine: `check(policy, ledger, request) → Decision`; `record(ledger, response)` ; in-memory + JSONL-backed ledger |
| `bin/policy_lint.py` | Lints `policy.json`: degrade-tier exists, kill switch ≥ 0, daily ≥ session ≥ call |
| `prompts/degrade-explainer.md` | Strict-JSON prompt that turns a `Decision(decision=allow_degraded, reason=...)` into a one-paragraph user-facing explanation |
| `examples/01-per-call-cap-trips-degrade/` | Worked example: a per-call cap trips on a long-context request; envelope returns `allow_degraded` with `tier=cheap`; ledger records the degraded spend |
| `examples/02-session-cap-trips-killswitch/` | Worked example: a session accumulates spend across five calls; the sixth trips the session cap whose `on_trip=kill`; envelope returns `deny`; subsequent calls in the same session also deny without re-evaluating |

## Adapt this section

Edit `policy.json`:

```json
{
  "version": 1,
  "tiers": {
    "default": {"input_per_1k": 0.003, "output_per_1k": 0.015},
    "cheap":   {"input_per_1k": 0.0005, "output_per_1k": 0.0015}
  },
  "caps": {
    "per_call":    {"usd": 0.20, "on_trip": "degrade", "degrade_to": "cheap"},
    "per_session": {"usd": 2.00, "on_trip": "kill"},
    "per_day":     {"usd": 25.00, "on_trip": "kill"}
  },
  "kill_switch_usd_remaining": null
}
```

`kill_switch_usd_remaining: 0.0` flips the global kill switch
(envelope denies every call until reset to `null`).

Then in your loop:

```python
dec = check(policy, ledger, request)
if dec.decision == "deny":
    raise BudgetExceeded(dec.reason)
if dec.decision == "allow_degraded":
    request = request.with_tier(dec.tier)
response = call_model(request)
record(ledger, response)
```

## Worked-example summary

| Example | Setup | Trip | Envelope decision |
|---|---|---|---|
| 01-per-call-cap-trips-degrade | per_call=$0.20, degrade_to=cheap; request projected $0.36 at default tier | per-call cap | `allow_degraded(tier=cheap, projected=$0.06)`; ledger records $0.06 actual |
| 02-session-cap-trips-killswitch | per_session=$2.00, on_trip=kill; five prior calls totalling $1.92; sixth call projected $0.18 | per-session cap | `deny(reason=session_cap_exceeded, headroom_usd=0.08, projected_usd=0.18)`; later 7th call in same session also `deny` without re-projection |

Both run end-to-end against the in-memory ledger. The expected
`Decision` shape and ledger state are documented in each example's
`README.md`.

## Cross-references

- `token-budget-tracker` — records spend after the fact, by model
  / phase / tool / cache bucket. This envelope's `record()` writes
  the same JSONL line shape so a single tracker can read both.
- `alert-noise-budget` — same operational vocabulary (budget,
  trip, back-off) for a different resource (alert volume).
- `tool-call-retry-envelope` — when degrade is chosen, the retry
  envelope's `idempotency_key` is *not* recomputed, so a retry of
  a degraded call replays the degraded result rather than
  re-promoting to the default tier.
- `failure-mode-catalog` — operational fix for "Runaway Session"
  and "Slow-Drip Daily Spend".
