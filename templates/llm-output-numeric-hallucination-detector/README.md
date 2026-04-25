# llm-output-numeric-hallucination-detector

Pure stdlib detector that flags **numeric hallucinations** in LLM output: a
number that appears in the model's response but does NOT appear in the source
context the model was supposed to ground against (system prompt + retrieved
documents + tool results).

## Problem

A JSON-schema validator can confirm the model returned `{"retention": 47.3,
"unit": "pct"}`. It cannot confirm the value `47.3` actually appeared in the
retrieved documents. The most damaging RAG bug class is exactly this — the
*shape* is right, the *content* is invented:

- "Retention rose to 47.3%" — context never said anything about retention.
- "Active accounts grew to 12,480" — context said "all customers"; model
  picked a plausible-looking number.
- "47% of users opted in" — context said "47 users"; the unit drift is the
  fabrication.

A schema-strict pipeline can't catch any of these, and by the time a human
notices, the bad output is already in the audit log.

## When to use

- RAG / agent-memory / summarization systems where the model must ground
  numeric claims in retrieved sources.
- As a post-output gate alongside `agent-output-validation` (shape) and
  `llm-output-language-mismatch-detector` (script). Run schema first, then
  numeric grounding.
- Daily / weekly digest generators where a hallucinated stat lands in a Slack
  message that nobody re-checks.

## Design

- **Five recognized numeric shapes**, each canonicalized to a `Number(value,
  unit)`:

  | shape | example | unit |
  |---|---|---|
  | percent | `47.3%`, `41%` | `pct` |
  | currency | `$1,247.50`, `$3` | `usd` |
  | year (1000–2999, in year context) | `in 2019` | `year` |
  | comma-grouped int / decimal | `12,480`, `8.5` | `raw` |
  | bare int | `47`, `12` | `raw` |

  `47%` and `47` are NOT equal — different units, different claims. A context
  that says `47 users` does not ground an output that says `47%`.

- **Year-vs-int resolution** uses the immediately preceding text. A bare
  4-digit number is `year` only when preceded by `in / since / during / by /
  as of / from / circa / until / after / before`. Else it's `raw`. Same digits
  with different units co-exist in the dedup set.

- **Comma normalization**: `1,247` and `1247` compare equal (caller can
  hand-mix and the detector still grounds them).

- **`rel_tol` opt-in**: default 0.0 (strict). Pass `rel_tol=0.01` to allow
  rounded outputs (`47.3%` matches a context `47.31%`). Tolerance only
  applies *within the same unit*.

- **`pinned_numbers` allowlist** for universally-safe values (`100%`, `0`).
  Caller-supplied; default empty.

- **Closed verdict enum**:

  | verdict | meaning | typical action |
  |---|---|---|
  | `clean` | every output number grounded | accept |
  | `partial` | mixed real-and-fake (the dangerous case) | re-prompt or quarantine |
  | `fabricated` | NO output numbers grounded | reject; model invented |
  | `no_numbers` | output had nothing to check | route to a different validator |

  `no_numbers` is distinct from `clean` so a pure-prose answer doesn't get
  silently rubber-stamped as "all numbers grounded — there were none."

- **Pure & deterministic**: `detect(output, context, *, pinned_numbers,
  rel_tol) -> NumericReport` does no I/O, no global state, replayable from
  JSONL.

## Files

- `detector.py` — `Number`, `NumericReport`, `NumericConfigError`, plus
  `extract_numbers()` and `detect()`. Stdlib only (`re`, `dataclasses`).
- `example.py` — five-scenario worked example (one per verdict + unit drift)
  plus year-vs-int extraction demo and pinned-allowlist demo.

## Worked example output

Captured by running `python3 templates/llm-output-numeric-hallucination-detector/example.py`:

```

=== Scenario 1: CLEAN — every output number grounded ===
  ctx  : Q3 retention report: 47.3% of users returned within 30 days, up from 41.2% in Q2. Total active accounts: 12,480. Average session length 8.5 minutes.
  out  : Retention rose from 41.2% to 47.3% quarter-over-quarter. Active accounts now 12,480.
  verdict     : clean
  output_nums : ['41.2%', '47.3%', '12480']
  grounded    : ['41.2%', '47.3%', '12480']
  ungrounded  : []
  ctx_size    : 5
  summary     : verdict=clean output_numbers=3 grounded=3 ungrounded=0 context_size=5

=== Scenario 2: FABRICATED — no output numbers in context ===
  ctx  : Q3 retention improved over Q2. Engagement is up.
  out  : Retention rose from 41.2% to 47.3%. Active accounts grew to 12,480 and average session length is 8.5 minutes.
  verdict     : fabricated
  output_nums : ['41.2%', '47.3%', '12480', '8.5']
  grounded    : []
  ungrounded  : ['41.2%', '47.3%', '12480', '8.5']
  ctx_size    : 0
  summary     : verdict=fabricated output_numbers=4 grounded=0 ungrounded=4 context_size=0

=== Scenario 3: PARTIAL — half real, half invented ===
  ctx  : Active accounts: 12,480. Quarter: Q3.
  out  : Active accounts hit 12,480, retention rose to 47.3%, and average revenue per user is $8.42.
  verdict     : partial
  output_nums : ['12480', '47.3%', '$8.42']
  grounded    : ['12480']
  ungrounded  : ['47.3%', '$8.42']
  ctx_size    : 1
  summary     : verdict=partial output_numbers=3 grounded=1 ungrounded=2 context_size=1

=== Scenario 4: UNIT DRIFT — context '47 users' != output '47%' ===
  ctx  : 47 users opted in to the beta.
  out  : 47% of users opted in to the beta.
  verdict     : fabricated
  output_nums : ['47%']
  grounded    : []
  ungrounded  : ['47%']
  ctx_size    : 1
  summary     : verdict=fabricated output_numbers=1 grounded=0 ungrounded=1 context_size=1

=== Scenario 5: NO_NUMBERS — prose-only answer ===
  ctx  : Active accounts: 12,480. Retention 47.3%.
  out  : Engagement improved this quarter, driven by the new onboarding flow.
  verdict     : no_numbers
  output_nums : []
  grounded    : []
  ungrounded  : []
  ctx_size    : 2
  summary     : verdict=no_numbers context_size=2

=== Extraction: year vs raw int (context word resolves ambiguity) ===
  'in 2019, sales hit 2019 units'
    -> [('2019', 'year'), ('2019', 'raw')]
  Note: first 2019 is year-tagged (preceded by 'in'); second 2019
        is unit='raw' (no year-context word) — dedup keys on (value, unit).

  'we shipped 2019 widgets'
    -> [('2019', 'raw')]
  Note: no year-context word -> unit='raw'

  'released in 2019; revenue 2019 dollars'
    -> [('2019', 'year'), ('2019', 'raw')]
  Note: BOTH units present (year + raw) — dedup keys on (value, unit).

=== Pinned allowlist: 100% is universally safe ===
  ctx  : All 12 servers reported in.
  out  : 100% of the 12 servers reported in.
  pinned: 100%
  verdict     : clean
  output_nums : ['100%', '12']
  grounded    : ['100%', '12']
  ungrounded  : []
  ctx_size    : 1
  summary     : verdict=clean output_numbers=2 grounded=2 ungrounded=0 context_size=1

=== all 6 verdicts asserted ===
```

## Composes with

- `agent-output-validation` / `llm-output-jsonschema-repair` — schema validates
  *shape*; this validates *content*. Run schema first, numeric grounding
  second (no point asking "are the numbers real?" if the JSON is malformed).
- `llm-output-language-mismatch-detector` — sibling content gate for natural
  language; this template is the sibling content gate for numeric claims.
- `structured-output-repair-loop` — a `partial` or `fabricated` verdict is
  the trigger to re-prompt with the explicit ungrounded list (`"the
  following numbers were not in your sources: ..."`) rather than a generic
  "try again."
- `agent-decision-log-format` — the `summary` field is shaped to drop
  directly into a one-line decision log entry.

## Limits / non-goals

- Numbers spelled in words (`"forty-seven percent"`) are out of scope. The
  conservative rule is: the model emitted a numeric token, the detector
  audits numeric tokens. Word-spelled numbers should be normalized
  upstream by a separate pass.
- Cross-unit reasoning (`"$1.50 each × 100 units = $150"`) is out of scope.
  This template grounds *individual* numbers, not derived arithmetic. A
  model that correctly multiplies but cites a wrong factor is caught
  (the wrong factor isn't in context); a model that computes correctly
  from valid factors and emits a *new* result that's not in context will
  be flagged as `partial` — the operator must decide whether their pipeline
  trusts derived numbers.
- Date strings (`"2024-03-15"`) are out of scope. The detector treats
  digits-with-hyphens as raw substrings, not dates. Use a date-specific
  validator if you need date grounding.
