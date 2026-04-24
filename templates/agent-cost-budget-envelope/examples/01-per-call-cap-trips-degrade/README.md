# Example 01 — per-call cap trips → degrade

## What this shows

A request asks for 100,000 input tokens and 4,000 output tokens at
the `default` tier. At default-tier prices ($0.003/1k input,
$0.015/1k output) the projected cost is $0.36 — over the per-call
cap of $0.20. The cap's `on_trip` is `degrade` with `degrade_to:
cheap`. The envelope re-projects at the cheap tier ($0.0005 / $0.0015
per 1k) → $0.056, well within the cap. Decision is `allow_degraded`
with `tier: cheap`. The ledger row carries `reason:
per_call_cap_exceeded` so reports can later distinguish "ran on the
cheap tier because it was the right tool" from "ran on the cheap
tier because the default would have busted the cap".

## Run

```bash
rm -f ledger.jsonl
python3 ../../bin/budget_envelope.py demo policy.json ledger.jsonl request.json
```

## Math

- Default tier: 100 × $0.003 + 4 × $0.015 = $0.300 + $0.060 = **$0.360**.
- per_call cap = $0.20 → tripped (0.36 > 0.20).
- degrade_to: cheap. Cheap tier: 100 × $0.0005 + 4 × $0.0015 = $0.050 + $0.006 = **$0.056**.
- 0.056 ≤ 0.20 → allowed at cheap.
- Session rollup = $0.00, day rollup = $0.00 → both clean.

## Expected stdout

```json
{
  "decision": "allow_degraded",
  "headroom_usd": 0.2,
  "projected_usd": 0.056,
  "reason": "per_call_cap_exceeded",
  "tier": "cheap"
}
```

## Expected ledger.jsonl (one row)

```jsonl
{"input_tokens": 100000, "output_tokens": 4000, "reason": "per_call_cap_exceeded", "session_id": "s_demo_01", "tier": "cheap", "ts": "2026-04-24T17:00:00Z", "usd": 0.056}
```

## What to do next

In a real loop the caller now passes the `tier: cheap` choice to
its model client and emits the `degrade-explainer` prompt's output
to the user so they know quality may differ. A second identical
request in the same session would re-evaluate from scratch — the
envelope is stateless per call beyond what the ledger has recorded.
