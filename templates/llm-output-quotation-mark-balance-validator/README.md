# llm-output-quotation-mark-balance-validator

Pure stdlib detector for unbalanced or mismatched quotation marks in
LLM prose. Catches the silent-corruption class where the model emits
"hello world without a closing quote, or mixes `"hello"` (straight)
with `“hello”` (curly) in a single document — the prose still reads
fluent but a downstream consumer that splits on quote spans, renders
to JSON, or diffs against a reference fails or misaligns.

Five quote families are tracked independently in a single pass:

- straight double  `"  ...  "`
- straight single  `'  ...  '`  (apostrophes in contractions like
  `don't` are filtered out by adjacency-to-letter heuristic)
- curly double  `“ ... ”`
- curly single  `‘ ... ’`
- backtick code spans  `` ` ... ` ``

## Why a separate template

Existing siblings cover adjacent layers:

- `llm-output-fence-extractor` — extracts fenced ` ``` ` code blocks.
  It does *not* check that inline backticks (single `` ` ``) are
  paired.
- `llm-output-jsonschema-repair` — repairs JSON envelope shape. By
  the time a curly “smart” quote has corrupted a JSON string value,
  the schema repairer can't tell whether the original intent was a
  literal char or a delimiter.
- `agent-output-validation` — validates structured outputs against
  a schema; says nothing about prose-level quote balance.

This template plugs the gap: it runs *before* JSON serialisation and
flags the cases where the model dropped a closing quote, mixed
straight and curly forms, or left an inline-code backtick open.

## Findings

Deterministic order: `(family, kind)` — two runs over the same input
produce byte-identical output.

| kind | severity | what it catches |
|---|---|---|
| `unbalanced_symmetric` | hard | odd count of a symmetric quote (straight double, straight single after apostrophe filtering, backtick) |
| `unmatched_open` | hard | curly family has more openers than closers (`“` without `”`) |
| `unmatched_close` | hard | curly family has more closers than openers (`”` without `“`) |
| `mixed_pairing` | configurable | the document mixes straight-double and curly-double *pairs* — disabled by default for casual prose, enabled by default in this template (`forbid_mixed_pairing=True`) because the most common consumer is JSON serialisation, which demands one canonical form |

`ok` is `False` iff any finding fires.

## Design choices

- **Apostrophe-aware single-quote counting.** Naive parity counting
  would fire on every contraction (`don't`, `it's`). Single quotes
  with a letter on either side are filtered as apostrophes by
  default. Disable via `skip_apostrophes=False` for source where
  every `'` really is a delimiter (e.g. shell-string output).
- **Curly families are open/close-aware.** Unicode gives us
  distinct `“` `”` `‘` `’` characters, so we can report `unmatched_open`
  vs `unmatched_close` separately — the caller knows which side the
  model dropped. Symmetric families (straight, backtick) can only be
  balanced by parity, so they get a single `unbalanced_symmetric`
  finding.
- **`forbid_mixed_pairing=True` by default.** The most common
  consumer of LLM prose is a downstream parser (JSON, CSV, regex
  extractor) that demands one canonical quote form. A document that
  mixes both is almost always going to break something. Flip it off
  for casual narrative output where curly quotes are stylistic.
- **Eager refusal on bad input.** `prose` not a string raises
  `QuotationValidationError` immediately.
- **Pure function.** No I/O, no clocks, no transport.
- **Stdlib only.** `dataclasses`, `json`. No `re`, even — straight
  string scans are enough.

## Composition

- `llm-output-fence-extractor` handles triple-backtick fenced
  blocks; this template handles inline single-backtick spans (and
  catches the case where a single backtick was left open before a
  fence).
- `llm-output-jsonschema-repair` runs *after* this template — if
  this template passes, the repairer can trust that curly-vs-straight
  quoting won't corrupt JSON string parsing.
- `agent-decision-log-format` — emit one log line per finding sharing
  `family` for queryable audit.
- `structured-output-repair-loop` can take an `unmatched_open`
  finding and feed it back as a one-shot repair hint ("you opened a
  curly double quote with `“` but never closed it with `”`").

## Run

```bash
python3 templates/llm-output-quotation-mark-balance-validator/example.py
```

Pure stdlib. No `pip install`. Five worked cases — clean, dropped
close double, curly opener without closer (apostrophe filtering
verified), backtick odd + mixed pairing, nested curly single
balanced.

## Example output

```
--- 01 clean ---
{
  "ok": true,
  "counts": {
    "straight_double": {
      "open": 4,
      "close": 4,
      "total": 4
    },
    "straight_single": {
      "open": 0,
      "close": 0,
      "total": 0
    },
    "curly_double": {
      "open": 0,
      "close": 0,
      "total": 0
    },
    "curly_single": {
      "open": 0,
      "close": 0,
      "total": 0
    },
    "backtick": {
      "open": 0,
      "close": 0,
      "total": 0
    }
  },
  "findings": []
}

--- 02 dropped close double ---
{
  "ok": false,
  "counts": {
    "straight_double": {
      "open": 1,
      "close": 1,
      "total": 1
    },
    "straight_single": {
      "open": 0,
      "close": 0,
      "total": 0
    },
    "curly_double": {
      "open": 0,
      "close": 0,
      "total": 0
    },
    "curly_single": {
      "open": 0,
      "close": 0,
      "total": 0
    },
    "backtick": {
      "open": 0,
      "close": 0,
      "total": 0
    }
  },
  "findings": [
    {
      "kind": "unbalanced_symmetric",
      "family": "straight_double",
      "count": 1,
      "detail": "odd number of straight double quotes (\") found: 1"
    }
  ]
}

--- 03 curly opener without closer + apostrophe ok ---
{
  "ok": false,
  "counts": {
    "straight_double": {
      "open": 0,
      "close": 0,
      "total": 0
    },
    "straight_single": {
      "open": 0,
      "close": 0,
      "total": 0
    },
    "curly_double": {
      "open": 1,
      "close": 0,
      "total": 1
    },
    "curly_single": {
      "open": 0,
      "close": 0,
      "total": 0
    },
    "backtick": {
      "open": 0,
      "close": 0,
      "total": 0
    }
  },
  "findings": [
    {
      "kind": "unmatched_open",
      "family": "curly_double",
      "count": 1,
      "detail": "curly double has 1 openers but 0 closers"
    }
  ]
}

--- 04 backtick odd + mixed pairing ---
{
  "ok": false,
  "counts": {
    "straight_double": {
      "open": 2,
      "close": 2,
      "total": 2
    },
    "straight_single": {
      "open": 0,
      "close": 0,
      "total": 0
    },
    "curly_double": {
      "open": 1,
      "close": 1,
      "total": 2
    },
    "curly_single": {
      "open": 0,
      "close": 0,
      "total": 0
    },
    "backtick": {
      "open": 1,
      "close": 1,
      "total": 1
    }
  },
  "findings": [
    {
      "kind": "unbalanced_symmetric",
      "family": "backtick",
      "count": 1,
      "detail": "odd number of backticks found: 1"
    },
    {
      "kind": "mixed_pairing",
      "family": "double",
      "count": 1,
      "detail": "prose mixes straight and curly double-quote pairs in a single document"
    }
  ]
}

--- 05 nested curly single + everything balanced ---
{
  "ok": true,
  "counts": {
    "straight_double": {
      "open": 0,
      "close": 0,
      "total": 0
    },
    "straight_single": {
      "open": 0,
      "close": 0,
      "total": 0
    },
    "curly_double": {
      "open": 1,
      "close": 1,
      "total": 2
    },
    "curly_single": {
      "open": 1,
      "close": 1,
      "total": 2
    },
    "backtick": {
      "open": 0,
      "close": 0,
      "total": 0
    }
  },
  "findings": []
}

=== summary ===
case 01: ok=True kinds=[]
case 02: ok=False kinds=['unbalanced_symmetric']
case 03: ok=False kinds=['unmatched_open']
case 04: ok=False kinds=['mixed_pairing', 'unbalanced_symmetric']
case 05: ok=True kinds=[]
```

The output proves the four invariants:

- **Case 01**: four straight double quotes (`"hello"` and `"hi"`) and
  one apostrophe (`It's`). The apostrophe is correctly filtered —
  `straight_single` total is `0` — and parity is even, so `ok=True`.
- **Case 02**: a single dropped closer is reported as
  `unbalanced_symmetric` on `straight_double` because that's the
  only signal a symmetric-quote family can give. Caller cannot tell
  whether the missing one is the opener or the closer — that's a
  fundamental limit of straight quotes, not a bug in the detector.
- **Case 03**: the curly opener `“` with no `”` is reported as
  `unmatched_open` on `curly_double`, with `count=1` saying exactly
  how many openers are stranded. The contraction `don't` is
  correctly filtered out of the straight-single count — no false
  positive.
- **Case 04**: a single piece of prose can produce *two independent*
  findings — one symmetric (`backtick` is odd) and one cross-family
  (`mixed_pairing` because the document uses both straight and
  curly double-quote pairs). Sorted deterministically by
  `(family, kind)`.
- **Case 05**: nested quoting (curly double around curly single)
  passes — both families are balanced, the templates do not assume
  flat structure, and `ok=True`.
