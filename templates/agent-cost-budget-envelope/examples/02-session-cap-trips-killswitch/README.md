# Example 02 — session cap trips → kill switch

## What this shows

A session has accumulated $1.92 over five prior model calls (see
`ledger.seed.jsonl`). The per-session cap is $2.00 with `on_trip:
kill` (no degrade tier on session — by policy, once a session is
exhausted you get out of the loop, not just cheaper). The sixth call
projects $0.18 at the default tier — under the per-call cap of
$0.50, but pushes the session rollup to $2.10 → over the session
cap.

The envelope returns `deny` with `reason: per_session_cap_exceeded`
and `headroom_usd: 0.08` (the room that *was* left on the cap). The
ledger is **not** appended — denies are observed in the caller's
exception path, not the spend log.

A seventh call in the same session, regardless of size, also denies
with the same reason and headroom. There is no "let me try a
smaller request to slip under" path; once the rollup is over the
cap, the session is done until it crosses a UTC day boundary or the
operator resets ledger / policy.

## Run

```bash
cp ledger.seed.jsonl ledger.jsonl
python3 ../../bin/budget_envelope.py demo policy.json ledger.jsonl request.json
# 6th call → deny

python3 ../../bin/budget_envelope.py demo policy.json ledger.jsonl request_7th.json
# 7th call → also deny, same reason
```

## Math

- Seed ledger: 5 rows summing to $1.920 (verify: 0.18 + 0.225 + 0.315 + 0.75 + 0.45 = 1.920).
- 6th request: 50k input × $0.003 + 2k output × $0.015 = 0.15 + 0.03 = **$0.18**.
- per_call cap = $0.50 → not tripped (0.18 ≤ 0.50).
- per_session rollup + projected = 1.92 + 0.18 = **$2.10** > $2.00 → tripped, on_trip=kill → **deny**.
- 7th request: 30k input × $0.003 + 1k output × $0.015 = 0.09 + 0.015 = **$0.105**.
- per_session rollup is still 1.92 (denies don't append). 1.92 + 0.105 = $2.025 > $2.00 → also **deny**.

## Expected stdout (6th call)

```json
{
  "decision": "deny",
  "headroom_usd": 0.08,
  "projected_usd": 0.18,
  "reason": "per_session_cap_exceeded",
  "tier": "default"
}
```

## Expected stdout (7th call)

```json
{
  "decision": "deny",
  "headroom_usd": 0.08,
  "projected_usd": 0.105,
  "reason": "per_session_cap_exceeded",
  "tier": "default"
}
```

## Expected ledger after both calls

Five rows, unchanged. Both denies are observed by the caller (which
should `raise BudgetExceeded(dec.reason)`); neither appends a row.

## What to do next

The on-call operator has two correct responses:

1. **Let it ride.** This session has spent its allotment. The agent
   should hand off to the user with the deny reason. Don't catch
   and retry — see `ENVELOPE.md` "Anti-pattern 5".
2. **Raise the cap deliberately.** Edit `policy.json` to bump
   `caps.per_session.usd` and document why. The next call
   re-evaluates against the new policy. Do **not** edit the
   ledger — that's history, not intent.

The kill-switch field (`kill_switch_usd_remaining`) is a separate
mechanism for incident response: setting it to `0.0` makes every
call across every session deny with `reason: kill_switch_engaged`
until reset to `null`.
