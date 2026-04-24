# Degrade-explainer prompt — agent-cost-budget-envelope

Render a `Decision(decision="allow_degraded", ...)` into a single
short paragraph explaining to the end user (or to a downstream
agent) **what tier was used and why**, without leaking the policy
file or speculating about future calls.

## Input

```json
{
  "decision": "allow_degraded",
  "tier": "cheap",
  "projected_usd": 0.06,
  "reason": "per_call_cap_exceeded",
  "headroom_usd": 0.20
}
```

## Output (strict JSON, single field)

```json
{
  "explanation": "This response was produced with the cheap tier because the request would have exceeded the per-call cost cap of $0.20. The cheap tier projected $0.06, well within budget. Output quality may differ from the default tier."
}
```

## Rules

1. Reference the cap that tripped (`per_call`, `per_session`,
   `per_day`) — but use plain English ("per-call cost cap"), not
   the field name.
2. Quote the projected USD and the headroom from the input.
   Do not invent numbers.
3. Always include one sentence about quality differing from the
   default tier — the user needs to know.
4. Never speculate about whether the next call will also degrade.
   The envelope re-evaluates each call.
5. If `reason="kill_switch_engaged"` or any `*_kill` deny code
   appears, the input is wrong — `decision` would be `"deny"`,
   not `"allow_degraded"`. Reject with
   `{"explanation": null, "error": "input_decision_must_be_allow_degraded"}`.
6. No emoji. No exclamation points. No "I". Third-person factual
   tone.

## Anti-patterns

- "We had to use the cheap tier to save you money!" — speculation
  about intent, anthropomorphic.
- "Quality will be lower." — over-claim. "May differ" is correct.
- Listing the policy file's contents — the user does not see the
  policy and shouldn't infer it from the explanation.
