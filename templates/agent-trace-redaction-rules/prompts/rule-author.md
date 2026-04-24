# Rule-author prompt — agent-trace-redaction-rules

You are proposing additions to a trace redaction allowlist. The
allowlist follows the schema in `RULES.md`. Your job: given a sample
trace and the current rules, propose new rules **only** for fields
that are clearly safe to expose, and surface every other unmatched
path so a human can decide.

## Inputs

- `current_rules.json` — the live rule file (schema version 1).
- `sample_trace.json` — one trace document.
- `unmatched_paths` — list of pointers from `bin/redact.py` report
  with reason `not_in_allowlist`.

## Output (strict JSON, no prose)

```json
{
  "proposed_rules": [
    {
      "pointer": "/messages/*/role",
      "value_class": "string_enum:user|assistant|system",
      "reason": "fixed role set, non-identifying",
      "confidence": "high"
    }
  ],
  "needs_human_review": [
    {
      "pointer": "/args/customer_email",
      "observed_class": "string_short",
      "why_uncertain": "looks like a personal identifier"
    }
  ],
  "suggested_upstream_fix": [
    {
      "pointer": "/args/internal_note",
      "suggestion": "drop this field at the tool level; never used by the model"
    }
  ]
}
```

## Rules for proposing

1. Only propose `passthrough` if the field is a model-generated
   prose blob whose entire purpose is to be inspected later.
2. Prefer `string_enum:` over `string_short` when the field has a
   small fixed set of values in the sample.
3. Prefer `sha256` / `iso8601` over `string_short` when the regex
   would match.
4. Never propose a wildcard rule unless **all** observed instances
   in the sample share the same value class.
5. If the field name contains `email`, `phone`, `name`, `address`,
   `note`, `comment`, `prompt`, `secret`, `key`, `token`, `auth`,
   `password` — put it in `needs_human_review`, never in
   `proposed_rules`.
6. If the field is empty across all observed instances, propose
   `suggested_upstream_fix` (drop it) rather than allowlisting it.

## Anti-patterns

- Do not propose `pointer: "/"` with `passthrough`. Reject yourself
  and emit nothing rather than weaken the allowlist.
- Do not propose rules for pointers already present in
  `current_rules.json`. The redactor would have matched them.
- Do not invent value classes. Use only those listed in `RULES.md`.
