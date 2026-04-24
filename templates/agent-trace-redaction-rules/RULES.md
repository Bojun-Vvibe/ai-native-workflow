# Rule schema — agent-trace-redaction-rules

## File format

`rules.json`:

```json
{
  "version": 1,
  "allow": [
    {"pointer": "/idempotency_key", "value_class": "sha256", "reason": "non-identifying digest"},
    {"pointer": "/attempt_number",  "value_class": "int",    "reason": "retry counter"},
    {"pointer": "/args/to",         "value_class": "string_short", "reason": "recipient handle, ≤64 chars"},
    {"pointer": "/messages/*/role", "value_class": "string_enum:user|assistant|system", "reason": "fixed role set"}
  ]
}
```

## Pointer syntax

- RFC 6901 JSON pointer: `/foo/bar/0/baz`
- `*` is a **single-segment wildcard**: `/messages/*/role` matches
  `/messages/0/role`, `/messages/1/role`, but **not**
  `/messages/0/tool_calls/0/role`.
- No recursive `**`. If you want a nested field allowed at every
  depth, write multiple rules. (Explicit > clever.)
- Trailing slash forbidden.
- Pointer `""` (empty string) refers to the root object — rarely
  useful, but legal.

## Value classes

| Class | Accepts | Rejection sentinel |
|---|---|---|
| `int` | JSON integer (no booleans) | `[REDACTED:value_class_mismatch]` |
| `float` | JSON number | `[REDACTED:value_class_mismatch]` |
| `bool` | `true` / `false` | `[REDACTED:value_class_mismatch]` |
| `string_short` | string, length ≤ 64, no run of ≥3 whitespace chars | `[REDACTED:value_class_mismatch]` |
| `string_enum:A\|B\|C` | string equal to one of the listed values | `[REDACTED:value_class_mismatch]` |
| `iso8601` | string parseable as `YYYY-MM-DDTHH:MM:SS[.fff][Z\|+HH:MM]` | `[REDACTED:value_class_mismatch]` |
| `sha256` | string of exactly 64 lowercase hex chars | `[REDACTED:value_class_mismatch]` |
| `passthrough` | any JSON value | (never rejected on class) |

`passthrough` exists for genuinely free-form fields like model
output. Use it sparingly and document in `reason`.

## Sentinel format guarantees

- All sentinels begin with `[REDACTED:` and end with `]`.
- The reason after the colon is one of:
  `not_in_allowlist`, `value_class_mismatch`, `pointer_collision`.
- Sentinels are inserted **as the value**, replacing the original.
  The key/index is preserved so downstream consumers see the same
  shape.
- Sentinels are not themselves redacted on a re-run (idempotent).

## Anti-patterns

1. **Allowing `/` with `passthrough`.** This disables the engine.
   `check_rules.py` flags this.
2. **Two rules with the same pointer.** Last-write-wins is too
   surprising. `check_rules.py` errors out.
3. **Wildcard in the leaf position with `passthrough`.** E.g.,
   `/args/*` with `passthrough` lets through any new field
   silently — defeats the allowlist. Use explicit per-field rules.
4. **Adding rules to make a failing CI run pass.** The whole point
   is that adding a new field to the trace fails CI until someone
   approves the new rule. Resist the temptation.

## Walk semantics

The engine walks the input **top-down, depth-first**:

1. For each leaf (non-object, non-array), look up the pointer in the
   compiled rule table (wildcards expanded against the actual path).
2. If no rule matches → emit `[REDACTED:not_in_allowlist]`, log to
   report.
3. If a rule matches but the value fails the class check → emit
   `[REDACTED:value_class_mismatch]`, log to report.
4. Container nodes (objects, arrays) are not themselves redacted;
   their leaves are.

This means an empty object passes through unchanged, which is
correct: there is nothing to leak.

## Report format

`bin/redact.py` emits a JSONL report (one line per redaction):

```jsonl
{"pointer": "/args/internal_note", "reason": "not_in_allowlist", "observed_class": "string_short"}
{"pointer": "/messages/2/role",    "reason": "value_class_mismatch", "observed_class": "string_short", "rule_class": "string_enum:user|assistant|system"}
```

Use the report to decide whether to (a) propose new rules,
(b) fix the upstream tool to stop emitting the field, or
(c) accept the redaction as correct.
