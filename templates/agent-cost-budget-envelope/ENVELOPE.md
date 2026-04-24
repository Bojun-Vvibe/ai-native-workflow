# Envelope spec — agent-cost-budget-envelope

## Policy schema (`policy.json`)

```json
{
  "version": 1,
  "tiers": {
    "<tier_name>": {
      "input_per_1k": <float USD>,
      "output_per_1k": <float USD>
    }
  },
  "caps": {
    "per_call":    {"usd": <float>, "on_trip": "degrade"|"kill", "degrade_to": "<tier_name>"?},
    "per_session": {"usd": <float>, "on_trip": "degrade"|"kill", "degrade_to": "<tier_name>"?},
    "per_day":     {"usd": <float>, "on_trip": "degrade"|"kill", "degrade_to": "<tier_name>"?}
  },
  "kill_switch_usd_remaining": null | <float>
}
```

### Constraints

- `version` MUST be 1.
- `tiers` MUST contain a tier named `default`.
- Every cap with `on_trip="degrade"` MUST set `degrade_to`.
- The named `degrade_to` tier MUST exist in `tiers`.
- `caps.per_day.usd >= caps.per_session.usd >= caps.per_call.usd`.
- `kill_switch_usd_remaining`:
  - `null` → switch is off; normal cap evaluation.
  - `0.0` → switch is engaged; envelope denies every call until
    reset.
  - `<positive float>` → soft cap on cumulative spend across all
    sessions/days until reset (used during incident-response
    cool-downs); each call decrements it.

## Request shape

```python
@dataclass
class Request:
    session_id: str
    tier: str               # which tier the caller plans to use
    projected_input_tokens: int
    projected_output_tokens: int
    timestamp: str          # ISO 8601, used to bucket the per-day rollup
```

## Decision shape

```python
@dataclass
class Decision:
    decision: str           # "allow" | "allow_degraded" | "deny"
    tier: str               # which tier to actually use
    projected_usd: float
    reason: str             # short machine-readable code
    headroom_usd: float | None  # how much room remained on the tripped cap
```

### `reason` codes

| Code | Means |
|---|---|
| `ok` | No cap tripped |
| `per_call_cap_exceeded` | Projected per-call cost > `caps.per_call.usd` |
| `per_session_cap_exceeded` | Session rollup + projected > `caps.per_session.usd` |
| `per_day_cap_exceeded` | Day rollup + projected > `caps.per_day.usd` |
| `kill_switch_engaged` | `kill_switch_usd_remaining` is `0.0` or insufficient |
| `unknown_tier` | Request named a tier not in `policy.tiers` |

## Evaluation order (deterministic)

1. If `kill_switch_usd_remaining == 0.0` → `deny / kill_switch_engaged`.
2. Project cost at the requested tier. If unknown tier → `deny / unknown_tier`.
3. Check `per_call`. If tripped:
   - `on_trip=kill` → `deny / per_call_cap_exceeded`.
   - `on_trip=degrade` → re-project at `degrade_to`; if still
     tripped, `deny / per_call_cap_exceeded`.
4. Check `per_session` (rollup + projected at the *current effective
   tier*). Same trip rule.
5. Check `per_day` (rollup + projected). Same trip rule.
6. Otherwise `allow` (or `allow_degraded` if step 3 demoted the
   tier).

This order means: a per-call trip never silently masks a
per-session trip; if a degraded tier brings the per-call cost into
range but the session is already busted, you still see the session
deny with the right `reason`.

## Ledger schema (JSONL)

One line per recorded response:

```jsonl
{"ts":"2026-04-24T17:01:02Z","session_id":"s_abc","tier":"default","input_tokens":120,"output_tokens":340,"usd":0.00546,"reason":"ok"}
{"ts":"2026-04-24T17:01:08Z","session_id":"s_abc","tier":"cheap","input_tokens":900,"output_tokens":120,"usd":0.00063,"reason":"per_call_cap_exceeded"}
```

The `reason` is the *envelope decision's* reason at the time the
call was authorised (`ok` for normal allow, the trip code for
`allow_degraded`). For `deny`, no row is written by `record()`; the
deny is observed in the caller's exception path.

`record()` is **append-only**. Day rollups are computed by scanning
lines whose `ts` falls in the same UTC day as the request. For
production, swap in a database query; the JSONL backend is for the
worked examples.

## Anti-patterns

1. **Recomputing `degrade_to` per call site.** The envelope owns
   that decision. If a call site re-checks and overrides, the
   ledger and the policy disagree.
2. **Logging successful denies as `usd=0`.** They aren't spend.
   Don't pollute the ledger; let the caller log denies separately
   if needed.
3. **Setting `per_call.usd` higher than `per_session.usd`.** The
   linter flags this. It would let one call burn the whole session
   budget.
4. **Resetting the kill switch by editing the JSONL.** Edit
   `policy.json` (set `kill_switch_usd_remaining` back to `null`)
   instead. The ledger is history; the policy is intent.
5. **Catching `BudgetExceeded` and retrying.** A deny that is
   immediately retried is the runaway-session failure mode wearing
   a different mask.

## What this envelope does NOT do

- It does not call the model. Wire it into your model client.
- It does not measure actual tokens used; it trusts what the
  caller passes to `record()`. Pair with provider response usage
  fields.
- It does not enforce concurrency limits. Two callers in the same
  session racing to `check()` can both pass the per-session cap
  before either calls `record()`. If you need that, wrap the
  check + call + record in a session-scoped lock.
