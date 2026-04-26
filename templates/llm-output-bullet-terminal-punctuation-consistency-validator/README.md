# `llm-output-bullet-terminal-punctuation-consistency-validator`

Pure stdlib consistency gate for bullet-list items inside an LLM
output blob. Catches the bug class where the model writes:

```
- first item.
- second item
- third item;
- fourth item.
```

Each individual line is fine; the *list* is not. The reader has to
guess whether the inconsistency is meaningful (it isn't), and any
downstream tool that joins items with `". "` produces broken prose.

Five finding kinds:

- `mixed_terminator` — items in the same list use different
  terminators (period, semicolon, comma, colon, exclamation, question,
  or none). Reported once per **minority** item with the full count
  table and the majority terminator.
- `trailing_whitespace` — an item's body ends with whitespace before
  the EOL (often invisible in the rendered Markdown, but breaks
  copy-paste-into-shell workflows).
- `empty_item` — item body is empty after stripping the marker and
  whitespace. The reader sees an orphan bullet.
- `sentence_in_fragment_list` — most items are short fragments (no
  internal sentence-ending punctuation) but at least one item
  contains a sentence-end midway, suggesting the model glued a whole
  paragraph into a single bullet.
- `inconsistent_capitalization` — first character of items mixes
  upper- and lower-case across the list. Reported once per
  **minority** item.

A "list" is a contiguous run of lines whose first non-whitespace
character matches one of the bullet markers `-`, `*`, `+`, or a
numeric `\d+\.` / `\d+\)` prefix, all sharing the same indent depth.
A blank line or dedent ends the list. Nested sublists are scanned as
their own lists; single-item lists skip the cross-item axes.

## When to use

- Pre-publish gate on any LLM-generated **status report / release
  note / runbook** that contains bullet lists. The fragment/sentence
  axis specifically catches the "model wrote a paragraph into one
  bullet" class.
- Pre-commit guardrail on LLM-drafted **postmortems** — bullet lists
  in incident timelines are the artifact most often skimmed, and
  inconsistent terminators make the skim harder.
- Audit step in a **review-loop** that promotes
  [`agent-output-validation`](../agent-output-validation/)'s
  `repair_once` policy: a `mixed_terminator` finding feeds the
  offending list back into the repair prompt with a single
  instruction ("normalize terminators to `<majority>`").
- Cron-friendly: findings are sorted by `(offset, kind, raw)` and
  the `counts` dict is rendered in a deterministic key order, so
  byte-identical output across runs makes diff-on-the-output a valid
  CI signal.

## Inputs / outputs

```
validate_bullets(text: str) -> list[Finding]

Finding(kind: str, offset: int, raw: str, detail: str)
```

- `text` — the LLM output to scan. Must be `str` (raises
  `ValidationError` otherwise).
- `Finding.raw` is the full bullet line (including the marker), so a
  reviewer reading the report does not have to jump back to the
  source to see what's wrong.
- `format_report(findings)` renders a deterministic plain-text
  report. Empty list → `"OK: bullet terminal punctuation is
  consistent.\n"`.

Pure function: no I/O, no Markdown parser, no language detection. The
detector applies a regex over each line and scans bullet groups in
isolation.

## Composition

- [`agent-output-validation`](../agent-output-validation/) — feed a
  finding's `offset` and `kind` into the repair prompt for a one-turn
  fix; this template is the validator behind the `repair_once` policy
  for prose outputs that contain bullet lists.
- [`structured-output-repair-loop`](../structured-output-repair-loop/) —
  the per-attempt validator inside the loop's `validate(attempt)`
  callback; the `counts` table makes a stuck loop detectable (same
  `kind` + same `counts` across attempts → bail).
- [`llm-output-quote-style-consistency-validator`](../llm-output-quote-style-consistency-validator/) —
  orthogonal: that template enforces quote-style consistency, this
  enforces bullet-terminal-punctuation consistency. Both use the
  same minority-rule, the same `Finding` shape, and the same stable
  sort, so a single CI step can union their findings.
- [`llm-output-list-marker-consistency-validator`](../llm-output-list-marker-consistency-validator/) —
  orthogonal: that template enforces marker-character consistency
  (`-` vs `*` vs `+`), this enforces what comes at the *end* of each
  item. Run both on the same blob.
- [`structured-error-taxonomy`](../structured-error-taxonomy/) —
  classifies as `do_not_retry / attribution=model` for
  `sentence_in_fragment_list` (model glued a paragraph into a bullet —
  has to be regenerated, not retried).

## Worked example

```
$ python3 example.py
```

Verbatim output:

```
=== 01-clean-period ===
input:
  | Daily summary:
  | - shipped two templates.
  | - ran the linter.
  | - pushed to main.
OK: bullet terminal punctuation is consistent.

=== 02-mixed-terminators ===
input:
  | Open items:
  | - review the migration plan.
  | - ping the on-call
  | - update the runbook;
  | - close the ticket.
FOUND 2 bullet finding(s):
  [mixed_terminator] offset=43 :: terminator=none; counts={'period': 2, 'none': 1, 'semicolon': 1}; majority=period
    line='- ping the on-call'
  [mixed_terminator] offset=62 :: terminator=semicolon; counts={'period': 2, 'none': 1, 'semicolon': 1}; majority=period
    line='- update the runbook;'

=== 03-trailing-whitespace ===
input:
  | Checklist:
  | - first item.
  | - second item.   
  | - third item.
FOUND 1 bullet finding(s):
  [trailing_whitespace] offset=27 :: item body ends with whitespace
    line='- second item.   '

=== 04-empty-item ===
input:
  | Topics:
  | - caching
  | - 
  | - batching
FOUND 1 bullet finding(s):
  [empty_item] offset=20 :: item body is empty after stripping
    line='- '

=== 05-sentence-in-fragment-list ===
input:
  | Risks:
  | - flaky tests
  | - stale cache
  | - The deploy step occasionally fails. Retry usually works.
  | - noisy alerts
FOUND 3 bullet finding(s):
  [inconsistent_capitalization] offset=37 :: first_char='T' class=upper; counts={'lower': 3, 'upper': 1}; majority=lower
    line='- The deploy step occasionally fails. Retry usually works.'
  [mixed_terminator] offset=37 :: terminator=period; counts={'none': 3, 'period': 1}; majority=none
    line='- The deploy step occasionally fails. Retry usually works.'
  [sentence_in_fragment_list] offset=37 :: item contains an internal sentence end; sibling items are short fragments
    line='- The deploy step occasionally fails. Retry usually works.'

=== 06-inconsistent-capitalization ===
input:
  | Next steps:
  | - Draft the spec.
  | - review with the team.
  | - Ship the change.
FOUND 1 bullet finding(s):
  [inconsistent_capitalization] offset=32 :: first_char='r' class=lower; counts={'lower': 1, 'upper': 2}; majority=upper
    line='- review with the team.'

```

Notes:

- Case 02 — three of four items end with `.`, one with nothing, one
  with `;`. The detector reports both minority items with the full
  count table; the majority is named explicitly so a repair prompt
  can be built with a single string interpolation.
- Case 03 — the trailing whitespace on `"- second item.   "` is
  invisible in rendered Markdown but breaks any tool that compares
  the bullet body to a known string. The detector pinpoints the
  offset of the body so a `sed` fix is mechanical.
- Case 04 — empty items can render as orphan bullets. Detected even
  though there's nothing to compare terminators against.
- Case 05 — the long item simultaneously trips three axes:
  `mixed_terminator` (it's the only item with a period),
  `inconsistent_capitalization` (`T` vs three lowercase siblings),
  and `sentence_in_fragment_list` (it contains an internal sentence
  end while siblings are fragments). All three findings sort
  together by offset, making the offending line obvious in the
  report.
- Case 06 — the lowercase first char on item 2 is the lone minority
  in a three-item list. The detector reports it with the alpha-only
  count table; non-alpha first chars (e.g. starting with a backtick)
  are excluded from the comparison.

## Files

- `validator.py` — pure stdlib detector + `format_report`
- `example.py` — six-case worked example
