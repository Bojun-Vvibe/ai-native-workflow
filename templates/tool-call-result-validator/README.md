# tool-call-result-validator

Validate tool-call results against a declared schema before feeding them back
into the next LLM turn. Catches drift between tool definition and tool output,
strips noisy extras, coerces obvious type mismatches, and produces a
"safe-for-llm" subset.

## When to use

- Your agent loop calls tools whose authors are not you (third-party APIs,
  user-supplied plugins, scraped HTML structured into JSON).
- You see the model occasionally repeat malformed fields or hallucinate based
  on a stray debug payload that leaked through.
- You want a typed boundary between "what the tool returned" and "what the
  model is allowed to see next turn."

## Why this exists

- LLMs faithfully echo whatever shape they last saw — including extra fields
  that should never have been observable.
- Tool authors drift; field renames and type changes are silent failures
  unless you assert at the boundary.
- A small typed contract at the seam is cheaper than a long debug session
  six turns later.

## How to run the example

```
python3 example.py
```

The script feeds 4 representative tool results (clean, extra field, missing
required, type-coerced) through the validator and prints both the validation
report and the safe-for-llm subset for each.

## Example output

```
============================================================
tool-call-result-validator — worked example
============================================================

--- case: ok ---
raw:    {'user_id': 42, 'name': 'Ada', 'email': 'ada@example.com'}
[OK] tool=lookup_user
safe-for-llm: {'user_id': 42, 'name': 'Ada', 'email': 'ada@example.com'}

--- case: extra_field ---
raw:    {'user_id': 7, 'name': 'Bo', 'email': 'bo@example.com', 'debug_token': 'xyz'}
[OK] tool=lookup_user
  extra fields:     ['debug_token']
safe-for-llm: {'user_id': 7, 'name': 'Bo', 'email': 'bo@example.com'}

--- case: missing_required ---
raw:    {'user_id': 11, 'name': 'Cy'}
[FAIL] tool=lookup_user
  missing required: ['email']
safe-for-llm: {'user_id': 11, 'name': 'Cy'}

--- case: type_coerced ---
raw:    {'user_id': '99', 'name': 'Di', 'email': 'di@example.com'}
[OK] tool=lookup_user
  coerced:          ['user_id']
safe-for-llm: {'user_id': 99, 'name': 'Di', 'email': 'di@example.com'}

============================================================
Summary: 1 clean pass, 1 extra-stripped, 1 hard fail, 1 coerced.
============================================================
```

## Lessons from real use

The most common failure mode is not type errors — it's extra fields leaking
debug or auth tokens into the conversation transcript. Default `allow_extra=False`
and review the report's `extra` list during incident triage; you'll find at
least one field per quarter that was never meant to be model-visible. Coercion
should be reserved for fields where you have a single canonical type and the
upstream tool is known-flaky; never coerce IDs across types silently in
production without logging.
