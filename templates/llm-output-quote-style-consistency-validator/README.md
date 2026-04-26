# `llm-output-quote-style-consistency-validator`

Pure stdlib consistency gate for quotation marks inside an LLM output
blob. Catches the bug class where the model silently mixes `"…"` with
`“…”` (or `'…'` with `‘…’`) inside the same status report / changelog
/ runbook. Each style is independently valid; the resulting text is
not safely diffable, grep-able, or copy-pasteable into a downstream
tool that round-trips ASCII.

Five finding kinds:

- `mixed_double_quote_style` — both straight `"` and smart `“`/`”`
  appear. Reported once per **minority** occurrence so the caller can
  grep them out by offset.
- `mixed_single_quote_style` — same axis, single quotes. In-word
  apostrophes (`don't`, `John's`, `it’s`) are stripped before counting
  so a single typographic apostrophe never trips the gate.
- `unbalanced_smart_double` — across the whole document, smart
  double-quote opens `“` ≠ closes `”`. Reported once at the offset
  of the first smart double quote.
- `unbalanced_smart_single` — same axis, single quotes (after
  stripping apostrophes).
- `mismatched_pair` — within a single line, `“` count ≠ `”` count.
  Catches the paste-and-truncate case where the model opened a quote
  on one line and the closer ended up on a different line, even when
  the document-level balance is fine.

"Minority" = the less common of two styles in the document. Ties
break by reporting the **second**-encountered style. If only one
style is present on an axis, the detector emits nothing for that
axis: this is a **consistency** gate, not a style enforcer.

## When to use

- Pre-publish gate on any LLM-generated **status report / release
  note / changelog** that downstream tools will grep with ASCII
  patterns (`grep '"foo"'` silently misses smart-quoted occurrences).
- Pre-commit guardrail on LLM-drafted **runbooks / postmortems** —
  smart quotes in a code-adjacent runbook get pasted into shells and
  break.
- Audit step in a **review-loop** that promotes
  [`agent-output-validation`](../agent-output-validation/)'s
  `repair_once` policy: a `mixed_double_quote_style` finding feeds
  the exact offending offset back into the repair prompt.
- Cron-friendly: findings are sorted by `(offset, kind, raw)`, so
  byte-identical output across runs makes diff-on-the-output a valid
  CI signal.

## Inputs / outputs

```
validate_quotes(text: str) -> list[Finding]

Finding(kind: str, offset: int, raw: str, detail: str)
```

- `text` — the LLM output to scan. Must be `str` (raises
  `ValidationError` otherwise).
- Returns the list of findings sorted by `(offset, kind, raw)`.
- `format_report(findings)` renders a deterministic plain-text report.

Pure function: no I/O, no Unicode normalization, no language model.
The detector counts characters and applies an in-word apostrophe
heuristic (`(?<=[A-Za-z])['’](?=[A-Za-z])`). It does **not** try to
reflow text or auto-correct quotes — that's a separate concern.

## Composition

- [`agent-output-validation`](../agent-output-validation/) — feed a
  finding's `offset` and `kind` into the repair prompt for a one-turn
  fix; this template is the validator behind the `repair_once` policy
  for prose outputs.
- [`structured-output-repair-loop`](../structured-output-repair-loop/) —
  the per-attempt validator inside the loop's `validate(attempt)`
  callback; minority-style fingerprints make a stuck loop detectable
  (same `kind` + same `raw` across attempts → bail).
- [`llm-output-iso8601-timestamp-format-validator`](../llm-output-iso8601-timestamp-format-validator/) —
  orthogonal: that template enforces timestamp-shape consistency,
  this enforces quote-style consistency. Both are minority-rule
  consistency gates with identical `Finding` shape and stable sort,
  so a single CI step can union their findings.
- [`structured-error-taxonomy`](../structured-error-taxonomy/) —
  classifies as `do_not_retry / attribution=model` for
  `unbalanced_smart_double` (the model dropped a closing quote — has
  to be regenerated, not retried).

## Worked example

```
$ python3 example.py
```

Verbatim output:

```
=== 01-clean-straight ===
input: 'The agent said "ack" and the reviewer said "ok".'
OK: quote style is consistent.

=== 02-mixed-double ===
input: 'Phase A "queued", phase B "ran", phase C “done”.'
FOUND 2 quote finding(s):
  [mixed_double_quote_style] offset=41 raw='“' :: style=smart; counts={'straight': 4, 'smart': 2}
  [mixed_double_quote_style] offset=46 raw='”' :: style=smart; counts={'straight': 4, 'smart': 2}

=== 03-mixed-single-with-apostrophes ===
input: "It said 'first' then 'second' then ‘third’; don't conflate this with John's apostrophe."
FOUND 2 quote finding(s):
  [mixed_single_quote_style] offset=35 raw='‘' :: style=smart; counts={'straight': 4, 'smart': 2}
  [mixed_single_quote_style] offset=41 raw='’' :: style=smart; counts={'straight': 4, 'smart': 2}

=== 04-unbalanced-smart-double ===
input: 'The model emitted “start of quote and forgot to close it.'
FOUND 2 quote finding(s):
  [mismatched_pair] offset=18 raw='“' :: line opens=1 closes=0
  [unbalanced_smart_double] offset=18 raw='“' :: open=1 close=0

=== 05-per-line-mismatched-pair ===
input: 'Line one opens “here\nline two is unrelated\nline three closes” there.'
FOUND 2 quote finding(s):
  [mismatched_pair] offset=15 raw='“' :: line opens=1 closes=0
  [mismatched_pair] offset=60 raw='”' :: line opens=0 closes=1

=== 06-clean-smart-only ===
input: 'The reviewer wrote “ship it” and moved on.'
OK: quote style is consistent.

```

Notes:

- Case 02 catches both members of the lone smart pair as minority
  occurrences — `counts={'straight': 4, 'smart': 2}` makes the
  majority obvious in the report.
- Case 03 demonstrates the apostrophe carve-out: `don't` and `John's`
  contain straight-single, and the fictional `it’s`-style typographic
  apostrophe between letters is also ignored. Only the surrounding
  *quoted phrases* `'first'`, `'second'`, `‘third’` participate in
  the count.
- Case 04 emits two findings at the same offset — the document-level
  `unbalanced_smart_double` and the per-line `mismatched_pair`. The
  paired emission is intentional: the per-line check pinpoints which
  line owns the unbalance.
- Case 05 shows the per-line check firing twice on a balanced
  document. The whole-document smart-double balance is `1==1`, so
  `unbalanced_smart_double` does **not** fire — only `mismatched_pair`
  does, on each of the two offending lines.
- Case 06 is clean: smart only, balanced. Single-style documents are
  always accepted.

## Files

- `validator.py` — pure stdlib detector + `format_report`
- `example.py` — six-case worked example
