# llm-output-citation-bracket-balance-validator

Pure stdlib validator for inline numeric citation brackets in LLM
prose: `[1]`, `[2, 3]`, `[1-3]`. Catches the silent-corruption class
where the model writes fluent text but the citation layer is broken:
an unclosed `[`, a stray `]`, a citation id higher than the
bibliography contains, a descending range like `[3-1]`, a duplicated
id inside one bracket, or a "skipped id" — the prose cites `[1]` then
jumps to `[3]` with `[2]` never appearing anywhere, which in practice
almost always means the model dropped a sentence.

## Why a separate template

Existing siblings cover adjacent layers:

- `citation-id-broken-link-detector` — checks that a citation id
  resolves to a real entry in the references list. Says nothing
  about bracket pairing or sequence density.
- `llm-citation-anchor-resolution-validator` — validates that named
  anchors in the text resolve to bibliography entries. Numeric
  brackets are a different surface.
- `llm-output-quotation-mark-balance-validator` — same family
  (paired-delimiter discipline) but for quotes.
- `llm-output-ordinal-sequence-gap-detector` — generic ordinal-gap
  detector over arbitrary sequences. This template specializes the
  pattern for the citation-bracket surface and adds the structural
  checks (unclosed bracket, descending range, duplicate-in-bracket,
  out-of-range) that are unique to citations.

This template plugs the gap. Run it before serialising the prose to
a downstream pipeline that splits on `[N]` spans.

## Findings

Deterministic order: `(kind, pos, detail)` — two runs over the same
input produce byte-identical output (cron-friendly diffing).

| kind | what it catches |
|---|---|
| `unclosed_bracket` | a `[` with no matching `]` later in the prose |
| `stray_close` | a `]` with no matching `[` earlier |
| `empty_citation` | `[]` or `[,]` with no content |
| `non_numeric` | a citation entry like `[1, x]` whose chunk is not a number or range — fires per offending chunk |
| `out_of_range` | citation id outside `[1, max_id]` (only when caller passes `max_id`) |
| `descending_range` | `[3-1]` where the high end comes first |
| `duplicate_in_same_bracket` | `[2, 2]` or `[1-3, 2]` where the same id appears twice in one bracket |
| `skipped_id` | the prose cites `[1]` and `[3]` but never `[2]` (only when `require_dense_sequence=True`, which is the default) |

`ok` is `False` iff any finding fires.

## Design choices

- **Citation intent inferred from digits.** A bracket is treated as a
  citation attempt if and only if the body contains a digit. Pure-text
  brackets like `[citation needed]` or `[TODO]` have no digits and
  pass through as ordinary prose. This is the cheapest signal that
  separates "the model is trying to cite" from "the model is writing
  meta-text in brackets" without a NLP layer.
- **Mixed content still validates.** `[1, two]` contains a digit, so
  it parses as a citation attempt; the literal `two` then fires
  `non_numeric` as a structured finding, not a parse refusal. The
  philosophy is "extract everything we can, report what's wrong" so
  the downstream consumer sees both the partially-valid id list
  *and* the structural problems.
- **`require_dense_sequence=True` by default.** A document that cites
  `{1, 3}` but never `2` is, in practice, almost always a dropped
  sentence — the model was emitting a paragraph that cited source 2
  and skipped over it. Default-on; flip to `False` for documents
  that legitimately cite a non-contiguous subset.
- **One forward scan, no regex.** Single pass, character-level. The
  bracket parser is small enough to audit.
- **Eager refusal on bad input.** `prose` not a `str` raises
  `CitationValidationError` immediately. Empty prose is *valid*
  (no citations, no findings).
- **Pure function.** No I/O, no clocks, no transport. Composes
  freely.
- **Stdlib only.** `dataclasses`, `json`. No `re`.

## Composition

- `citation-id-broken-link-detector` — run *after* this template.
  This one validates structural shape (paired brackets, contiguous
  ids); the link detector validates that each id actually resolves
  to a bibliography entry. Different bug classes, same data flow.
- `llm-output-fence-extractor` — strip fenced code blocks first if
  the prose mixes code (which legitimately uses `[]` for arrays);
  feed only the narrative spans into this validator.
- `agent-decision-log-format` — one log line per finding, sharing
  `pos` so a reviewer can jump to the offending span.
- `structured-error-taxonomy` — `unclosed_bracket` /
  `stray_close` / `non_numeric` → instrumentation bug in the
  prompt template; `out_of_range` / `skipped_id` → the model
  hallucinated the citation graph.

## Worked example

Run `python3 example.py` from this directory. Eight cases — one
clean, seven each demonstrating a distinct finding family. The
output below is captured verbatim from a real run.

```
# llm-output-citation-bracket-balance-validator — worked example

## case 01_clean
prose: 'Recent work [1] confirms the trend. Earlier surveys [2, 3] disagree, and a meta-analysis [1-3] reconciles them.'
max_id=3, require_dense_sequence=True
{
  "cited_ids": [
    1,
    2,
    3
  ],
  "findings": [],
  "ok": true
}

## case 02_unclosed_bracket
prose: 'The reviewer cites [1, 2 and walks away mid-sentence.'
max_id=5, require_dense_sequence=True
{
  "cited_ids": [],
  "findings": [
    {
      "detail": "'[' with no matching ']'",
      "kind": "unclosed_bracket",
      "pos": 19
    }
  ],
  "ok": false
}

## case 03_skipped_id
prose: 'First, see [1]. Then jump straight to [3] without ever citing source 2.'
max_id=3, require_dense_sequence=True
{
  "cited_ids": [
    1,
    3
  ],
  "findings": [
    {
      "detail": "id 2 never cited (cited up to 3)",
      "kind": "skipped_id",
      "pos": -1
    }
  ],
  "ok": false
}

## case 04_out_of_range
prose: 'Combining [1], [2] and [9] (the bibliography only has three entries).'
max_id=3, require_dense_sequence=True
{
  "cited_ids": [
    1,
    2,
    9
  ],
  "findings": [
    {
      "detail": "citation [9] outside [1, 3]",
      "kind": "out_of_range",
      "pos": 23
    },
    {
      "detail": "id 3 never cited (cited up to 9)",
      "kind": "skipped_id",
      "pos": -1
    },
    {
      "detail": "id 4 never cited (cited up to 9)",
      "kind": "skipped_id",
      "pos": -1
    },
    {
      "detail": "id 5 never cited (cited up to 9)",
      "kind": "skipped_id",
      "pos": -1
    },
    {
      "detail": "id 6 never cited (cited up to 9)",
      "kind": "skipped_id",
      "pos": -1
    },
    {
      "detail": "id 7 never cited (cited up to 9)",
      "kind": "skipped_id",
      "pos": -1
    },
    {
      "detail": "id 8 never cited (cited up to 9)",
      "kind": "skipped_id",
      "pos": -1
    }
  ],
  "ok": false
}

## case 05_descending_and_duplicate
prose: 'A reverse range [3-1] and a doubled id [2, 2] both look fluent in prose.'
max_id=5, require_dense_sequence=True
{
  "cited_ids": [
    2
  ],
  "findings": [
    {
      "detail": "range goes backwards: '3-1'",
      "kind": "descending_range",
      "pos": 16
    },
    {
      "detail": "id 2 appears twice in the same bracket '2, 2'",
      "kind": "duplicate_in_same_bracket",
      "pos": 39
    },
    {
      "detail": "id 1 never cited (cited up to 2)",
      "kind": "skipped_id",
      "pos": -1
    }
  ],
  "ok": false
}

## case 06_non_numeric_inside_bracket
prose: 'Some authors write [1, x] when they mean to insert an id later.'
max_id=3, require_dense_sequence=True
{
  "cited_ids": [
    1
  ],
  "findings": [
    {
      "detail": "non-numeric entry: 'x'",
      "kind": "non_numeric",
      "pos": 19
    }
  ],
  "ok": false
}

## case 07_stray_close_bracket
prose: 'An accidental ] with no opener is easy to miss.'
max_id=3, require_dense_sequence=True
{
  "cited_ids": [],
  "findings": [
    {
      "detail": "']' with no matching '['",
      "kind": "stray_close",
      "pos": 14
    }
  ],
  "ok": false
}

## case 08_dense_off
prose: 'Sources [1] and [3] only — but require_dense_sequence is off so no skipped_id fires.'
max_id=3, require_dense_sequence=False
{
  "cited_ids": [
    1,
    3
  ],
  "findings": [],
  "ok": true
}
```

The output above is byte-identical between runs — `_CASES` is a fixed
list, the validator is a pure function, and findings are sorted by
`(kind, pos, detail)` before serialisation.

## Files

- `example.py` — the validator + the runnable demo.
- `README.md` — this file.

No external dependencies. Tested on Python 3.9+.
