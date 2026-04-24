# Example 02 — nested-fields-with-pointer

## What this shows

A dataset record nests cost telemetry under `meta.cost.{tokens_in,
tokens_out, user_id}`. Pointer-anchored rules let through the two
billing counters but redact `user_id` (no rule) **without** opening
the parent object to a wildcard. Separately, one of the messages has
`role: "tool"` which is not in the role enum — the engine catches
that with `value_class_mismatch` instead of letting an unexpected
role string leak.

## Run

```bash
python3 ../../bin/redact.py rules.json input.json output.json --report report.jsonl --strict
echo $?  # 2 — strict mode + redactions occurred
```

## Expected stdout

```
redactions: 2
```

## Expected exit code

`2` — `--strict` plus redactions present. Wire this into CI to fail
the build until the allowlist or the upstream tool is fixed.

## Expected output.json (excerpt)

```json
{
  "messages": [
    {"role": "user", "content": "what's our deploy SLA?"},
    {"role": "assistant", "content": "Two business days for non-emergency."},
    {"role": "[REDACTED:value_class_mismatch]", "content": "lookup_sla() → 2bd"}
  ],
  "meta": {
    "cost": {
      "tokens_in": 412,
      "tokens_out": 88,
      "user_id": "[REDACTED:not_in_allowlist]"
    }
  }
}
```

## Expected report.jsonl

```jsonl
{"observed_class": "string_short", "pointer": "/meta/cost/user_id", "reason": "not_in_allowlist"}
{"observed_class": "string_short", "pointer": "/messages/2/role", "reason": "value_class_mismatch", "rule_class": "string_enum:user|assistant|system"}
```

## What to do next

Two distinct decisions:

1. `user_id` — almost certainly not safe to expose. Drop upstream
   or hash it before it enters the trace.
2. `role: "tool"` — the system genuinely uses a tool role; widen
   the enum to `user|assistant|system|tool` if that is intended,
   or fix the producer to map tool-results into the assistant turn
   shape if that is the contract.

The lint passes (`check_rules.py` reports `ok: 4 rule(s)`); the
issue is in the data, not the rules.
