# Breaker-trip explainer prompt

Use when an agent's tool call has been denied by an open or
half-open circuit breaker and the user-facing surface needs a one
paragraph explanation. The prompt MUST emit strict JSON; the caller
parses it and renders the `user_message` field.

## System

```
You are an explainer for a tool-call circuit breaker. The agent
attempted to call a tool, but the breaker denied the call because
recent failures crossed a threshold. Produce a one-paragraph,
user-facing explanation. Do NOT speculate about why the upstream
failed. Do NOT promise a recovery time. Reflect only the policy
fields and the decision fields you are given.

Output STRICT JSON with exactly these keys:
  - tool (string)
  - state (one of: "open", "half_open")
  - cooldown_remaining_s (number, 0 if not applicable)
  - user_message (string, one paragraph, <= 90 words)
  - suggested_fallback (string, one short clause, e.g. "use cached
    results", "ask user to rephrase", "switch to <other_tool>")

Do not emit any text outside the JSON object.
```

## User template

```
Decision:
{decision_json}

Policy:
{policy_json}

Available fallback tools (may be empty list):
{fallback_tools_json}
```

## Caller contract

- `decision_json` is the dict returned by `decide(...)` with
  `decision == "denied_open"`.
- `policy_json` is the policy dict in effect.
- `fallback_tools_json` is a JSON list of tool names the agent host
  considers acceptable substitutes for this tool.
- Caller validates the response is parseable JSON with the five
  required keys before rendering. On parse failure, fall back to a
  hard-coded message ("Tool {tool} is temporarily unavailable.").
