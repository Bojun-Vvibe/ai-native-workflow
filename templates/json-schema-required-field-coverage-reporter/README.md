# json-schema-required-field-coverage-reporter

Per-required-field coverage reporter for a corpus of LLM JSON outputs. Walks a
JSON Schema, finds every required leaf path (including required leaves inside
nested required objects and inside `items` of required arrays), and reports
how often the *whole corpus* satisfies each path — `present`, `missing`,
`null`, `wrong_type` — plus the worst offender.

This is the artifact you reach for when:

- per-doc validation says `73%` and you want to know **which** required field
  the model keeps forgetting before you rewrite the prompt
- you're A/B-testing two system prompts and need a per-field delta, not a
  pass-rate delta
- you want to fail CI when one specific required field's miss rate crosses a
  threshold (e.g., `/summary` missing > 10% on the canary set)

## Why this template

Schema validators answer "is this one document valid?" with `True / False`.
That answer is useless when the model emits 200 documents and 60 fail — the
question you actually want answered is:

> Of the 60 failures, are they all missing the same field, or scattered?

Without this, prompt iteration is by anecdote ("I saw it forget `findings`
once"). With this, you fix the field with the highest miss rate first and you
have a number that goes down.

## What it walks

A useful subset of JSON Schema (the shape used by ~95% of LLM-output schemas):

- top-level `{type: object, required: [...], properties: {...}}`
- nested required objects (recursively)
- required arrays whose `items` is `{type: object, properties, required}` —
  every element of the array must satisfy the inner required leaves; an empty
  array counts the inner leaves as `missing`
- per-leaf `type ∈ {string, integer, number, boolean, array, object, null}`

It is **not** a full draft-2020-12 validator (no `oneOf`, `allOf`, `$ref`,
`pattern`, `enum`, conditional schemas). For per-doc strict validation pair
this with `agent-output-validation` or `tool-call-result-validator`.

## Verdict priority for array-of-object aggregation

For a path like `/findings[]/severity`, the aggregate per-doc verdict is the
**worst** verdict across all elements, with priority:

```
missing > wrong_type > null > present
```

So one element with no `severity` plus nine elements with `severity` still
counts the document as `missing` for that path. This is intentional: the
prompt has to instruct the model to fill *every* required field on *every*
element; "got it right 9/10 times in one response" is not yet a passing
behavior.

## Quirks worth knowing

- `bool` is rejected for `integer` fields even though `isinstance(True, int)`
  is `True` in Python. The model emitting `true` where you wanted `1` is
  almost certainly a bug in your prompt's example, not a feature.
- Empty enclosing array → inner leaves counted as `missing`, not skipped.
- Worst-offender ties broken by schema declaration order — predictable beats
  clever.

## Files

- `reporter.py` — pure stdlib reporter (~210 lines)
- `example.py` — 10-document corpus exercising every verdict, runnable
  via `python3 example.py`

## Worked example output

Schema is a code-review summary object with `findings: [{file, line, severity}]`
and `metadata: {model, elapsed_ms}`. The 10-document corpus contains 4 docs
missing `summary`, 1 with `summary: null`, 1 with `severity` missing on the
sole finding, 1 with `findings` empty, and 1 with `line` as a string.

Verbatim output of `python3 example.py`:

```
========================================================================
Coverage report — 10-document corpus against code-review schema
========================================================================
{
  "documents_total": 10,
  "documents_all_required_present": 2,
  "documents_with_at_least_one_missing": 6,
  "worst_offender_path": "/summary",
  "worst_offender_missing_rate": 0.5,
  "fields": [
    {
      "path": "/verdict",
      "expected_type": "string",
      "counts": { "present": 10, "missing": 0, "null": 0, "wrong_type": 0 },
      "rates":  { "present": 1.0, "missing": 0.0, "null": 0.0, "wrong_type": 0.0 }
    },
    {
      "path": "/summary",
      "expected_type": "string",
      "counts": { "present": 5, "missing": 4, "null": 1, "wrong_type": 0 },
      "rates":  { "present": 0.5, "missing": 0.4, "null": 0.1, "wrong_type": 0.0 }
    },
    {
      "path": "/findings",
      "expected_type": "array",
      "counts": { "present": 10, "missing": 0, "null": 0, "wrong_type": 0 },
      "rates":  { "present": 1.0, "missing": 0.0, "null": 0.0, "wrong_type": 0.0 }
    },
    {
      "path": "/findings[]/file",
      "expected_type": "string",
      "counts": { "present": 9, "missing": 1, "null": 0, "wrong_type": 0 },
      "rates":  { "present": 0.9, "missing": 0.1, "null": 0.0, "wrong_type": 0.0 }
    },
    {
      "path": "/findings[]/line",
      "expected_type": "integer",
      "counts": { "present": 8, "missing": 1, "null": 0, "wrong_type": 1 },
      "rates":  { "present": 0.8, "missing": 0.1, "null": 0.0, "wrong_type": 0.1 }
    },
    {
      "path": "/findings[]/severity",
      "expected_type": "string",
      "counts": { "present": 8, "missing": 2, "null": 0, "wrong_type": 0 },
      "rates":  { "present": 0.8, "missing": 0.2, "null": 0.0, "wrong_type": 0.0 }
    },
    {
      "path": "/metadata",
      "expected_type": "object",
      "counts": { "present": 10, "missing": 0, "null": 0, "wrong_type": 0 },
      "rates":  { "present": 1.0, "missing": 0.0, "null": 0.0, "wrong_type": 0.0 }
    },
    {
      "path": "/metadata/model",
      "expected_type": "string",
      "counts": { "present": 10, "missing": 0, "null": 0, "wrong_type": 0 },
      "rates":  { "present": 1.0, "missing": 0.0, "null": 0.0, "wrong_type": 0.0 }
    },
    {
      "path": "/metadata/elapsed_ms",
      "expected_type": "integer",
      "counts": { "present": 9, "missing": 1, "null": 0, "wrong_type": 0 },
      "rates":  { "present": 0.9, "missing": 0.1, "null": 0.0, "wrong_type": 0.0 }
    }
  ]
}

INVARIANTS OK — worst offender: /summary (missing+null+wrong_type rate 0.50)
```

(The above JSON whitespace is condensed slightly for the README; the actual
script emits one count/rate field per line. Counts and rates are byte-identical.)

## Reading the report

- `documents_all_required_present` (2/10) is the per-doc pass rate you'd get
  from a vanilla validator
- `worst_offender_path` (`/summary`, 50%) tells you the *first* prompt fix:
  the model is forgetting `summary` more than it forgets every other field
- the per-field `null` column is the difference between "the model didn't
  emit the key" and "the model emitted `null`" — those usually have different
  prompt fixes (the first wants a clearer `required:` callout, the second
  wants an example with a real value)

## Composes with

- `agent-output-validation` — per-document pass/fail; this aggregates across
  the whole corpus for prompt diagnostics
- `prompt-regression-snapshot` — re-run this reporter against last week's
  corpus and the new corpus; the per-field rate delta is the regression signal
- `evaluation-confidence-bands` — wrap each reported rate in a confidence
  interval before deciding whether a 0.50 → 0.42 drop is real
- `agent-decision-log-format` — log one line per coverage run with the worst
  offender + rate so you can grep across days

## Non-goals

- Not a full JSON Schema validator (no `oneOf`, `allOf`, `$ref`, `enum`,
  `pattern`, conditional)
- Doesn't validate *content* — `severity: "warn"` and `severity: "warbling"`
  both count as `present` for a `string` field
- Doesn't aggregate across multiple schemas in one pass (one schema per call)
- Doesn't write the prompt fix for you — it tells you which field to fix; you
  still write the example
