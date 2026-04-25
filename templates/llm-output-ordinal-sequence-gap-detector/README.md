# llm-output-ordinal-sequence-gap-detector

Pure stdlib detector for *gaps and duplicates* in ordinal sequences
inside LLM prose. Catches the silent-corruption class where the model
emits "Step 1 ... Step 2 ... Step 4" — the prose reads fluent, but a
downstream consumer that splits on "Step N:" or extracts a numbered
list ends up with a hole.

Six sequence kinds are tracked independently in a single pass:
`step`, `phase`, `stage`, `chapter`, `numbered` (lines starting `1.`
or `2)`), and `ordinal_word` (`first..twelfth`).

## Why a separate template

Existing siblings cover adjacent layers:

- `llm-output-list-count-mismatch-detector` — checks that a *count
  claim* ("here are 5 items") matches the items rendered. It does
  **not** notice that the items are labelled 1, 2, 4.
- `prompt-message-role-sequence-validator` — validates message-role
  alternation in a chat transcript, not ordinal anchors in prose.
- `agent-output-validation` / `structured-output-repair-loop` —
  validate JSON envelopes, not the human-readable enumeration inside
  a `prose` field.

This template plugs the gap: the JSON is valid, the count claim
matches the count of items, but the items themselves enumerate
1, 2, 4.

## Findings

Deterministic order: `(sequence, kind, value)` — two runs over the
same input produce byte-identical output.

| kind | severity | what it catches |
|---|---|---|
| `missing` | hard | sequence has a hole between min and max (1,2,4 → missing 3) |
| `duplicate` | hard | same ordinal emitted twice in the same sequence ("Step 2 ... Step 2") |
| `does_not_start_at_one` | hard | min ordinal > 1 ("Step 2: ..." with no Step 1) — disable via `require_start_at_one=False` for prose that legitimately picks up mid-sequence |

`ok` is `False` iff any finding fires. There are no warning-tier
findings: every gap or duplicate in an ordinal sequence is a real
defect.

## Design choices

- **Six sequence kinds, all in one pass.** A document can mix a
  numbered list and a "Step N:" enumeration in the same paragraph;
  each is reported as its own sequence so the caller can see exactly
  which enumeration broke.
- **Eager refusal on bad input.** `prose` not a string raises
  `OrdinalValidationError` immediately. Silent-empty would mask bugs
  upstream.
- **`require_start_at_one=True` by default.** "Step 2 begins by..."
  with no Step 1 is almost always an editing artefact (a deleted
  Step 1). Caller flips it off for legitimately-mid-sequence prose.
- **`flag_duplicates=True` by default.** A duplicated ordinal almost
  always means the model regenerated a paragraph and forgot to
  renumber.
- **Pure function.** No I/O, no clocks, no transport.
- **Stdlib only.** `re`, `dataclasses`, `json`.

## Composition

- `agent-output-validation` validates the JSON envelope shape (does
  it have a `prose` field?). This template validates the *contents*
  of that prose enumerate cleanly.
- `structured-output-repair-loop` can take a `missing` finding and
  feed it back as a one-shot repair hint ("you wrote Step 1, Step 2,
  Step 4 — either add Step 3 or renumber Step 4 to Step 3").
- `agent-decision-log-format` — emit one log line per finding sharing
  `sequence` for queryable audit.
- `llm-output-list-count-mismatch-detector` — that template checks
  *cardinality* claims against rendered items; this template checks
  the *labels* on those items are contiguous.

## Run

```bash
python3 templates/llm-output-ordinal-sequence-gap-detector/example.py
```

Pure stdlib. No `pip install`. Five worked cases — clean numbered
list, step gap, ordinal-word gap, duplicate phase + does-not-start-
at-one, and mixed (numbered ok, step has gap).

## Example output

```
--- 01 clean numbered list ---
{
  "ok": true,
  "sequences": {
    "numbered": [
      1,
      2,
      3
    ]
  },
  "findings": []
}

--- 02 step gap ---
{
  "ok": false,
  "sequences": {
    "step": [
      1,
      2,
      4
    ]
  },
  "findings": [
    {
      "kind": "missing",
      "sequence": "step",
      "value": 3,
      "detail": "step sequence has gap: value 3 missing between 1 and 4"
    }
  ]
}

--- 03 ordinal words skip third ---
{
  "ok": false,
  "sequences": {
    "ordinal_word": [
      1,
      2,
      4
    ]
  },
  "findings": [
    {
      "kind": "missing",
      "sequence": "ordinal_word",
      "value": 3,
      "detail": "ordinal_word sequence has gap: value 3 missing between 1 and 4"
    }
  ]
}

--- 04 duplicate phase + does-not-start-at-one ---
{
  "ok": false,
  "sequences": {
    "phase": [
      2,
      3
    ]
  },
  "findings": [
    {
      "kind": "does_not_start_at_one",
      "sequence": "phase",
      "value": 2,
      "detail": "phase sequence starts at 2 (expected 1)"
    },
    {
      "kind": "duplicate",
      "sequence": "phase",
      "value": 2,
      "detail": "phase value 2 appears 2 times"
    }
  ]
}

--- 05 mixed: numbered ok, step has gap ---
{
  "ok": false,
  "sequences": {
    "step": [
      1,
      3
    ],
    "numbered": [
      1,
      2,
      3
    ]
  },
  "findings": [
    {
      "kind": "missing",
      "sequence": "step",
      "value": 2,
      "detail": "step sequence has gap: value 2 missing between 1 and 3"
    }
  ]
}

=== summary ===
case 01: ok=True kinds=[]
case 02: ok=False kinds=['missing']
case 03: ok=False kinds=['missing']
case 04: ok=False kinds=['does_not_start_at_one', 'duplicate']
case 05: ok=False kinds=['missing']
```

The output proves the four invariants:

- **Case 01**: a clean `1./2./3.` list produces `ok=True` with no
  findings — the detector is not chatty about correct prose.
- **Case 02**: the `Step 4` after `Step 1, Step 2` is reported as a
  single `missing` finding pinned to value `3`, not as "Step 4 is
  unexpected" — the gap is the defect, not the surviving anchor.
- **Case 03**: ordinal words (`First`/`Second`/`Fourth`) are
  recognised as the `ordinal_word` sequence and produce the same
  shape of finding as digit-form sequences. Case-insensitive,
  word-boundary-anchored.
- **Case 04**: a single sequence can produce *two independent*
  findings (`duplicate` for repeated `Phase 2`, and
  `does_not_start_at_one` because the min is `2`). They're sorted
  deterministically by `(sequence, kind, value)`.
- **Case 05**: two sequences in the same prose are tracked
  independently — the `numbered` list is clean, the `step`
  enumeration has a gap, and only the gap is reported.
