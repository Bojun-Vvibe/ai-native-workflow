# `llm-output-acronym-first-use-expansion-checker`

Pure stdlib checker for the LLM-prose failure mode where an acronym
is used WITHOUT a preceding expansion at its FIRST occurrence in the
document — the artifact where the model writes "the SLO was met" in
the opening paragraph and only later (or never) defines `SLO` as
"service-level objective". The model has the binding in its weights
so it does not feel the need to expand; the human reader (especially
one outside the model's training distribution) does.

The bug is invisible at preview time but surfaces when:

- the doc is read by an audience without the same domain context as
  the model's training distribution (a CFO reading a platform
  postmortem; a junior engineer reading a senior's design doc),
- downstream summarization / RAG retrieval keys on the acronym
  string and loses the expansion entirely (the expansion in
  paragraph 7 never makes it into the chunk that contains the first
  reference in paragraph 1),
- the doc is auto-translated and the translator passes the acronym
  through without the target-language expansion the reader needs.

Five finding kinds, sorted by `(offset, kind)` for byte-identical
re-runs:

- `undefined_first_use` — acronym appears for the first time with NO
  expansion preceding it in the document. Fired on every undefined
  acronym (even single uses). The detail string carries the acronym
  and the sentence so the repair prompt is one interpolation away.
- `never_expanded` — acronym appears at least `min_repeats` times
  (default 2) and is NEVER expanded anywhere. Distinct severity from
  `undefined_first_use` because a one-off undefined acronym is
  often acceptable, but a repeatedly-used one without a binding is
  almost always wrong.
- `inconsistent_expansion` — same acronym, MULTIPLE expansions with
  DIFFERENT long forms (e.g. `LLM (large language model)` and later
  `LLM (language learning module)`). Almost always a model artifact;
  expansion drift across paragraphs is a strong signal the model
  lost the binding.
- `redundant_re_expansion` — same acronym re-expanded with the SAME
  long form. Soft warning kind — readers do not need the second
  `service-level objective (SLO)` once the binding is established.
  Useful for tightening prompts; demote to info-level if your house
  style allows re-expansion at section boundaries.
- `lowercase_after_acronym` — a lowercased form of an acronym
  introduced uppercase appears later as a standalone word. Often a
  model artifact where the model briefly forgets the term is an
  acronym and writes it as an ordinary noun.

An "acronym candidate" is a token of `≥ min_len` (default 2) ASCII
uppercase letters, optionally followed by a digit suffix (`SLO`,
`HTTP2`, `TLS13`). A configurable `allowlist` (default: a small set
of universally-known software-engineering acronyms — `OK`, `URL`,
`API`, `JSON`, `HTTP`, `HTTPS`, `CSS`, `HTML`, `SQL`, `XML`, `YAML`,
`CSV`, `PDF`, `RAM`, `CPU`, `GPU`, `OS`, `UI`, `UX`, `ID`, `PR`,
`CI`, `CD`, `IO`, `AM`, `PM`, `UTC`, `TCP`, `UDP`, `DNS`, `TLS`,
`SSL`, `SSH`, `IP`, `MAC`, `USB`, `SDK`, `IDE`, `REST`, `RPC`,
`TODO`, `FAQ`, …) is NEVER flagged. `extra_known` lets the caller
pre-declare project-specific acronyms (`RPO` for the team that knows
what it means).

Inside fenced code blocks (` ``` ` / `~~~`), inline code spans
(`` `...` ``), and Markdown link URLs (the `(...)` half of
`[text](url)`), tokens are SKIPPED. URLs frequently contain
uppercase tokens that are not English acronyms (`AWS_REGION` env
var, `X-Real-IP` header) and would false-positive heavily.

## When to use

- Pre-publish gate on any LLM-generated **design doc**, **incident
  postmortem**, **release-notes blob**, or **runbook** intended for
  a mixed-audience surface (engineering + product + leadership).
- Pre-flight for an LLM-drafted **PR description** or **issue body**
  before `gh` writes it to a permanent record. The acronym density
  in the first paragraph is the single highest predictor of "the
  reviewer asks what XYZ means in the comments".
- Audit step in a review-loop that promotes
  [`agent-output-validation`](../agent-output-validation/)'s
  `repair_once` policy: an `undefined_first_use` finding feeds the
  acronym + sentence back into the repair prompt with one
  instruction ("expand `<acronym>` at first use as
  `<long form> (<acronym>)`").
- Cron-friendly: findings are sorted by `(offset, kind)` and the
  report is rendered deterministically, so byte-identical output
  across runs makes diff-on-the-output a valid CI signal.

## Inputs / outputs

```
detect_acronym_issues(text: str, *,
                      allowlist: set[str] | None = None,
                      min_len: int = 2,
                      min_repeats: int = 2,
                      extra_known: set[str] | None = None,
                      ) -> list[Finding]

Finding(kind, line_number, column, offset, acronym, sentence, detail)
```

- `text` — the LLM output to scan. Must be `str` (raises
  `ValidationError` otherwise).
- `allowlist` — overrides the default universal set entirely.
- `extra_known` — additive: project-specific acronyms treated as
  always-defined.
- `min_len` — minimum acronym length (default 2). Single-letter
  uppercase tokens (a sentence-initial `I`) are never candidates.
- `min_repeats` — for `never_expanded` only; an acronym must occur
  at least this many times to escalate from `undefined_first_use`.
- `Finding.line_number` is 1-based; `Finding.column` is 1-based;
  `Finding.offset` is the 0-based byte offset in the original text
  so editor jump-to-byte works against the source.
- `Finding.sentence` is the trimmed sentence containing the offending
  acronym (truncated to ~160 chars with `...` if longer) so a
  reviewer reading the report alone has enough context.
- `format_report(findings)` renders a deterministic plain-text
  report. Empty list → `"OK: all acronyms expanded at first use.\n"`.

Pure function: no I/O, no Markdown parser, no language detection.

## Composition

- [`agent-output-validation`](../agent-output-validation/) — feed a
  finding's `(acronym, sentence, kind)` into the repair prompt.
  `undefined_first_use` is the canonical case — the repair prompt
  asks the model to insert `<long form> (<acronym>)` at the
  offending sentence.
- [`structured-output-repair-loop`](../structured-output-repair-loop/) —
  the `(offset, kind, acronym)` tuple is a stable fingerprint; same
  tuple twice in a row → bail rather than burn another turn.
- [`llm-output-quote-style-consistency-validator`](../llm-output-quote-style-consistency-validator/),
  [`llm-output-bullet-terminal-punctuation-consistency-validator`](../llm-output-bullet-terminal-punctuation-consistency-validator/),
  [`llm-output-emphasis-marker-consistency-validator`](../llm-output-emphasis-marker-consistency-validator/) —
  orthogonal typographic / structural validators on the same `text`
  blob. Same fence-awareness convention, same deterministic sort,
  so a single CI step can union them.
- [`llm-output-trailing-whitespace-and-tab-detector`](../llm-output-trailing-whitespace-and-tab-detector/) —
  orthogonal: invisible-byte hygiene vs reader-comprehension
  hygiene. Both deterministic, both cron-friendly.
- [`structured-error-taxonomy`](../structured-error-taxonomy/) —
  classifies as `do_not_retry / attribution=model` for
  `undefined_first_use`, `never_expanded`, `inconsistent_expansion`
  (a same-prompt retry will reproduce the binding loss); the soft
  `redundant_re_expansion` is `info` and never fails CI.

## Worked example

```
$ python3 example.py
```

Verbatim output:

```
=== 01-clean ===
input:
  | We met our service-level objective (SLO) for the quarter.
  | The SLO target was 99.9 percent availability.
  | Our recovery point objective (RPO) was also met.
OK: all acronyms expanded at first use.

=== 02-undefined-first-use ===
input:
  | The SLO was met for the quarter and the team is on track.
  | Owners should review the dashboard before the next review.
FOUND 1 acronym finding(s):
  [undefined_first_use] line=1 col=5 off=4 :: acronym 'SLO' first used at byte 4 with no preceding expansion in the document
    sentence='The SLO was met for the quarter and the team is on track.'

=== 03-never-expanded-repeated ===
input:
  | The RPO was reviewed in the meeting.
  | The RPO target is unchanged from last quarter.
  | Future RPO reviews will be scheduled monthly.
FOUND 2 acronym finding(s):
  [never_expanded] line=1 col=5 off=4 :: acronym 'RPO' used 3 times, never expanded
    sentence='The RPO was reviewed in the meeting.'
  [undefined_first_use] line=1 col=5 off=4 :: acronym 'RPO' first used at byte 4 with no preceding expansion in the document
    sentence='The RPO was reviewed in the meeting.'

=== 04-inconsistent-expansion ===
input:
  | We use a large language model (LLM) for the summarization step.
  | Later in the pipeline a second language learning module (LLM) handles the rerank.
FOUND 1 acronym finding(s):
  [inconsistent_expansion] line=2 col=1 off=64 :: acronym 'LLM' expanded as 'later in the pipeline a second language learning module' but earlier expanded as 'we use a large language model'
    sentence='Later in the pipeline a second language learning module (LLM) handles the rerank.'

=== 05-redundant-re-expansion ===
input:
  | The service-level objective (SLO) was met for the quarter.
  | The dashboard is healthy.
  | As a reminder, the service-level objective (SLO) is the contract we publish to consumers.
FOUND 1 acronym finding(s):
  [redundant_re_expansion] line=3 col=16 off=100 :: acronym 'SLO' re-expanded as 'the service-level objective' (already established)
    sentence='As a reminder, the service-level objective (SLO) is the contract we publish to consumers.'

=== 06-lowercase-and-allowlist ===
input:
  | The service-level objective (SLO) was met.
  | Later in the doc the slo target was reviewed by the team.
  | The API is documented in the wiki.
FOUND 1 acronym finding(s):
  [lowercase_after_acronym] line=2 col=22 off=64 :: lowercase 'slo' appears after acronym 'SLO' was introduced — likely model artifact
    sentence='Later in the doc the slo target was reviewed by the team.'

```

Notes:

- Case 01 — proves the happy path. `SLO` is introduced as
  `service-level objective (SLO)` so the immediate next reference
  `The SLO target was …` is correctly NOT flagged. `RPO` is also
  expanded in its own sentence.
- Case 02 — `SLO` is used at offset 4 of byte 0 with no expansion
  anywhere in the doc. The single-use case fires only
  `undefined_first_use`, not `never_expanded`, because `min_repeats`
  defaults to 2.
- Case 03 — `RPO` used three times and never expanded. Both
  `undefined_first_use` AND `never_expanded` fire, sharing the same
  offset (the first occurrence). The two findings sort together so
  the reviewer sees both severities for the same acronym in
  adjacent lines of the report.
- Case 04 — `LLM` expanded twice with different long forms. The
  detail string carries BOTH forms verbatim so the reviewer can
  decide which is correct (or whether the model actually meant two
  distinct concepts and chose a colliding acronym). The first-use
  expansion is treated as the established binding; the SECOND
  distinct expansion is what fires.
- Case 05 — `SLO` legitimately defined in paragraph 1, then
  redundantly re-defined in paragraph 3. The soft warning fires
  with the long form and the offset. A house style that allows
  re-expansion at section boundaries can filter this kind out at
  the CI step.
- Case 06 — proves both the lowercase-after-acronym detection
  (`slo` flagged because `SLO` was introduced earlier) AND the
  allowlist behavior (`API` is in the default allowlist and is
  correctly NOT flagged even though it has no expansion).

## Files

- `validator.py` — pure stdlib detector + `format_report`
- `example.py` — six worked-example cases (run: `python3 example.py`)
- `README.md` — this file

## Limitations

- The expansion regex is greedy on the long-form side (up to 8
  trailing tokens before the `(ACR)` parenthesis). Case 04 shows
  this: the second expansion is reported as `"later in the pipeline
  a second language learning module"` rather than just `"language
  learning module"`. The report is still actionable — the reader
  immediately sees the inconsistency — but a downstream tool that
  programmatically extracts the long form should trim leading
  filler words before consuming.
- Sentence detection is naive (`. `, `! `, `? `, `\n\n`, `\n`). An
  acronym that appears inside `e.g.` will get a truncated sentence
  in the report. The `Finding.offset` is still byte-accurate.
- Single-letter uppercase tokens are never candidates (`min_len`
  default 2), so a sentence-initial `I` or a standalone `A`
  reference does not fire.
- The default allowlist is software-engineering biased. For a
  domain (medical, legal, finance) where different acronyms are
  universal, pass an explicit `allowlist` covering that vocabulary
  or use `extra_known` to extend the default.
- The lowercase-after-acronym heuristic uses a small built-in
  English stop set to avoid flagging common 3-letter words that
  happen to collide with acronyms. The conservative check ("the
  doc must have introduced the uppercase form first") already
  eliminates most false positives. If your doc legitimately uses
  the lowercase as a different word (`PR` the acronym vs `pr`
  unlikely, but possible), filter the kind out at the CI step.
- An acronym that appears AT LEAST ONCE expanded somewhere in the
  document, but whose FIRST occurrence is BEFORE the expansion,
  fires `undefined_first_use` (not `never_expanded`). The fix is
  to move the expansion earlier in the doc; the model often
  defines an acronym in the conclusion section after using it
  freely throughout.
