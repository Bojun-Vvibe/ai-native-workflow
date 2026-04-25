# llm-output-jsonschema-repair

Cheap, deterministic, **local-only** repair pass for LLM outputs that
are supposed to match a JSON Schema but don't quite. Applied before
you spend a round-trip asking the model to "please fix the JSON".

## What problem it solves

When you ask an LLM to emit a JSON object against a schema, you get
five common shapes back:

1. Clean, valid JSON.
2. JSON wrapped in <code>```json … ```</code> fences, often with a
   one-line "Sure, here you go:" preamble.
3. JSON with smart quotes (`"` `"` `'` `'`) or trailing commas.
4. Valid JSON missing a required field that has a schema-declared
   default.
5. Valid JSON with a field that's the wrong type but losslessly
   coercible (`"42"` where the schema wants `integer`, `"false"`
   where it wants `boolean`).

Cases 2–5 are not really model-quality failures — they're cosmetic.
Round-tripping them back through the model costs a full inference and
adds 1–10s of latency before the agent can move on. This repair pass
fixes them locally, deterministically, and records exactly what it
did.

For genuinely broken outputs (missing required fields with no default,
type mismatches that aren't coercible, additional properties when
`additionalProperties: false`), it returns a structured violation
list so the caller can decide whether to escalate to a model
round-trip, fall back to the previous good value, or quarantine.

## When to use it

- Ahead of any model round-trip-for-repair loop. Use this first; only
  call the model again if `ok=False` and the violations look like real
  semantic gaps.
- Anywhere you parse structured agent output (tool-call arguments,
  evaluator verdicts, planner outputs).
- As a standardization pass — even when the JSON parses, the repair
  pass injects defaults so downstream code can rely on every required
  field being present.

## When NOT to use it

- You need full JSON Schema compliance including `oneOf`/`anyOf`,
  pattern matching, `format`, `$ref`, etc. This module supports a
  practical subset (`type`, `properties`, `required`, `default`,
  `enum`, `items`, `additionalProperties`). Pull in `jsonschema` for
  full draft compliance.
- Your downstream system can't tolerate any auto-coercion. If
  `"42" → 42` would silently mask a bug, run with coercion disabled
  (or fork the module — coercion is centralized in
  `_coerce_to_type`).
- The output is naturally non-JSON (markdown prose, code, etc.).

## Files

- `repair.py` — `repair(raw, schema) -> RepairResult`. Stdlib only.
- `worked-example/run.py` — five fixtures, one per failure mode,
  including one irrecoverable case.

## What it does and does NOT repair

| Input pathology | Repaired? | How |
|---|---|---|
| Code fences (<code>```json … ```</code>) | yes | regex strip |
| Conversational preamble ("Sure, here is…") | yes | regex strip |
| Smart quotes | yes | unicode → ASCII |
| Trailing commas in objects/arrays | yes | regex |
| Missing required field, schema has `default` | yes | inject default |
| Missing required field, **no** default | no | recorded as violation |
| Wrong type, losslessly coercible | yes | type coercion |
| Wrong type, lossy / ambiguous | no | recorded as violation |
| Extra properties when `additionalProperties: false` | yes | dropped |
| Enum violation | no | recorded as violation |
| Unbalanced braces / fundamentally broken JSON | no | parse error |

## Demo

```
--- fenced_with_preamble ---
  ok=True
  repairs=['strip_conversational_preamble', 'strip_code_fence']
  violations=[]
  value={"confidence": 0.82, "follow_ups": ["bump retry budget", "add trace id"], "repo": "acme-ci/runner", "verdict": "approve"}

--- smart_quotes_and_trailing_commas ---
  ok=True
  repairs=['normalize_smart_quotes', 'strip_trailing_commas']
  violations=[]
  value={"confidence": 0.41, "follow_ups": ["fix flaky test"], "repo": "acme-ci/runner", "verdict": "request_changes"}

--- missing_required_with_default ---
  ok=True
  repairs=['default_required:/verdict', 'drop_additional:/extra_chatter']
  violations=[]
  value={"confidence": 0.55, "follow_ups": [], "repo": "acme-ci/runner", "verdict": "comment"}

--- type_mismatch_coercible ---
  ok=True
  repairs=['coerce_number:/confidence', 'coerce_boolean:/is_blocking']
  violations=[]
  value={"confidence": 0.73, "follow_ups": ["look at flake rate"], "is_blocking": false, "repo": "acme-ci/runner", "verdict": "comment"}

--- irrecoverable_missing_required ---
  ok=False
  repairs=[]
  violations=['missing_required:/repo']
  value={"confidence": 0.9, "follow_ups": [], "verdict": "approve"}

summary: 4 accepted, 1 quarantined out of 5 fixtures
self-check: OK
```

Four of five fixtures land cleanly with no model round-trip. The fifth
(missing `repo` with no default) is the one a sensible host would
actually escalate to either a model retry or a human.
