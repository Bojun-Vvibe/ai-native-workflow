# `tool-call-argument-schema-coercer`

A coercion layer that sits between the model and your tool dispatch.
Takes loose LLM-emitted argument dicts and either (a) returns a clean,
strictly-typed dict ready to invoke the tool with, or (b) returns a
structured **repair prompt** the model can act on in a single follow-up
turn.

Stdlib only. No `jsonschema` dependency. Schemas are tiny dicts.

## What it solves

The model emits arguments that are *almost* right. Real failures from
the wild:

- `user_id: "4421"` (string, schema wants int)
- `when_epoch: "2025-01-01T00:00:00Z"` (ISO string, schema wants epoch)
- `urgent: "yes"` (stringified bool)
- `note: null` (schema has a default; null should fall back, not crash)
- `retries: 99` (out of range; need to tell the model the bound)
- `phantom_field: "..."` (model invented a field; should be surfaced
  for the repair turn, not silently dropped)

Three bad common reactions to this:

1. **Reject hard, ask the model to retry.** Wastes a round trip and
   the model often makes the same mistake.
2. **Coerce silently with `try/except` everywhere.** Loses the audit
   trail; you can't tell whether the model said `True` or `"true"`.
3. **Pass through and let the tool crash.** Side effects may have
   already happened by the time the tool raises.

The coercer makes the policy explicit and one-shot recoverable.

## When to use

- You wrap N tools with deterministic argument schemas.
- You'd rather repair-once than reject-and-retry-loop.
- You want the host to log exactly which fields were coerced and which
  were defaulted, separately from fields that arrived clean.

## When NOT to use

- Your schemas are deeply nested / polymorphic — use a real schema
  validator (`jsonschema`, `pydantic`).
- Your tool is non-idempotent and the cost of a coercion mistake is
  catastrophic — pair the strict validator with
  `tool-call-retry-envelope` for safe replay.
- The model is already producing strict typed JSON via constrained
  decoding. Then you only need the bounds check, not the coercion.

## Anti-patterns this prevents

- **Bool from arbitrary string**: only `{true, t, yes, y, 1, on}` and
  the falsy mirror are accepted. `"maybe"` fails loudly.
- **`bool` smuggled as `int`**: `True` is rejected for `int` fields
  even though Python says `isinstance(True, int)`.
- **Float-to-int silent truncation**: `3.7 -> 3` is *not* allowed.
  `3.0 -> 3` is.
- **Stringified-everything**: `str` fields don't accept arbitrary
  objects; only `int`/`float`/`bool`/`str`. Lists and dicts as `str`
  fail (they would lose structure).
- **Marker / default ambiguity**: defaults are recorded in
  `defaulted_fields`; explicit user-supplied values are not, so you
  can later distinguish "model said retries=3" from "we filled in 3".

## Schema mini-language

```python
{
  "field_name": {
    "type": "int" | "float" | "bool" | "str" | "epoch_seconds",
    "required": True | False,        # default False
    "default": <value>,              # used when missing OR null
    "min": <num>, "max": <num>       # optional bounds (numeric/epoch)
  }
}
```

`epoch_seconds` accepts: an int, a numeric string, an ISO-8601 string
(with or without `Z`). Naive datetimes are assumed UTC.

## API surface

`coerce(schema, args) -> CoerceResult`

| Field on `CoerceResult` | Meaning |
|---|---|
| `ok` | True if every required field was present and every value coerced + bounded successfully. |
| `args` | Coerced, defaulted, ready-to-dispatch dict. Empty if `not ok`. |
| `errors` | List of `FieldError(field, reason, got)`. Always populated when `not ok`. |
| `coerced_fields` | Fields whose value type changed during coercion. |
| `defaulted_fields` | Fields that fell back to their declared default. |
| `unknown_fields` | Fields present in input but not in the schema. Surfaced for repair, not auto-dropped. |
| `.repair_prompt()` | Pre-formatted instruction the model can act on in one follow-up turn. |

## Sample output

Running `python3 worked_example.py` against a `schedule_followup`
tool with a 5-field schema and five realistic call shapes:

```
=== clean call ===
input:  {'user_id': 4421, 'when_epoch': 1735689600, 'urgent': True, 'note': 'renew profile'}
OK -> {'user_id': 4421, 'when_epoch': 1735689600, 'urgent': True, 'note': 'renew profile', 'retries': 3}
  defaulted: ['retries']

=== string ints + ISO date + stringified bool ===
input:  {'user_id': '4421', 'when_epoch': '2025-01-01T00:00:00Z', 'urgent': 'yes', 'note': 'renew profile', 'retries': '5'}
OK -> {'user_id': 4421, 'when_epoch': 1735689600, 'urgent': True, 'note': 'renew profile', 'retries': 5}
  coerced:   ['user_id', 'when_epoch', 'urgent', 'retries']

=== nulls take defaults; missing optional omitted ===
input:  {'user_id': 7, 'when_epoch': 1700000000, 'urgent': False, 'note': None}
OK -> {'user_id': 7, 'when_epoch': 1700000000, 'urgent': False, 'note': '', 'retries': 3}
  defaulted: ['note', 'retries']

=== retries above max + unknown field ===
input:  {'user_id': 7, 'when_epoch': 1700000000, 'urgent': False, 'retries': 99, 'phantom_field': 'ignored at coerce, surfaced for repair'}
FAIL -> repair prompt for the model:
Your tool call had argument errors. Fix and resend:
  - field 'retries': value 99 above max 10 (got: 99)
  - unknown fields (drop them): ['phantom_field']

=== required missing + non-numeric string ===
input:  {'when_epoch': 'not-a-date', 'urgent': 'maybe'}
FAIL -> repair prompt for the model:
Your tool call had argument errors. Fix and resend:
  - field 'user_id': required field missing (got: <missing>)
  - field 'when_epoch': expected epoch_seconds, unparseable date string (got: 'not-a-date')
  - field 'urgent': expected bool, string not in known truthy/falsy set (got: 'maybe')

summary: 3 ok, 2 need repair (of 5 total)
invariants OK
```

Three things to notice in the output:

1. **Case 2 turns four loose-typed fields into one ready-to-dispatch
   dict** — including the ISO date `2025-01-01T00:00:00Z` becoming
   epoch `1735689600`. The host didn't have to re-prompt.
2. **Case 4's repair prompt names both the bound violation
   (`retries=99 above max 10`) and the phantom field** in one
   message, so a single repair turn fixes both.
3. **Case 5 surfaces all three errors at once** instead of one-at-a-
   time. The model can fix everything in one follow-up rather than
   N rejected turns.

## Wiring it in

```python
from coercer import coerce

def dispatch(tool_name, raw_args):
    schema = SCHEMAS[tool_name]
    result = coerce(schema, raw_args)
    if not result.ok:
        return ("repair", result.repair_prompt())
    log_event("tool_args_coerced",
              tool=tool_name,
              coerced=result.coerced_fields,
              defaulted=result.defaulted_fields)
    return ("invoke", TOOLS[tool_name](**result.args))
```

The two log fields (`coerced`, `defaulted`) are what you grep for
later when tuning prompts: if the same field shows up in
`coerced_fields` 1000 times a day, your tool description in the
system prompt is misleading the model about that field's type.

## Files

- `coercer.py` — `coerce`, `CoerceResult`, `FieldError`.
- `worked_example.py` — five realistic argument-shape cases against a
  five-field tool schema.
