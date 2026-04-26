# `llm-output-markdown-bullet-marker-consistency-validator`

Pure stdlib consistency gate for the unordered-list bullet marker
character (`-`, `*`, `+`) inside an LLM markdown output. Catches the
bug class where the model silently switches marker style mid-list, or
emits one block of dashes followed by another block of asterisks
inside the same document. The rendered HTML is identical, but the raw
markdown stops being grep-able and any pinned linter
(`markdownlint MD004`, prettier) immediately rejects it.

Three finding kinds:

- `mixed_marker_in_list` — within one contiguous list block, more
  than one marker character appears. Reported once per **minority**
  bullet line so the caller can fix them by line/column.
- `mixed_marker_in_document` — across the whole document, separate
  list blocks use different dominant markers. Reported once at the
  first bullet of each minority block.
- `inconsistent_indent_marker` — at the same indent depth (after
  tab-expansion), more than one marker is used. Catches nested-bullet
  drift even when each individual block looks internally clean.

"Minority" = the less common of the markers seen on that axis. Ties
break by reporting the **lower-ordinal** marker as majority (so `-`
beats `*` beats `+`). Single-marker documents emit nothing on every
axis: this is a **consistency** gate, not a style enforcer.

## When to use

- Pre-publish gate on any LLM-generated **status report / changelog
  / runbook** that downstream tools will lint with a pinned bullet
  marker (`markdownlint` MD004 default is `consistent`, prettier
  rewrites to a single style — both reject mixed input).
- Pre-commit guardrail on LLM-drafted **READMEs** in repos that
  already standardize on one marker — the validator's `majority`
  field tells the auto-fixer which character to keep.
- Audit step in a **review-loop** that promotes
  [`agent-output-validation`](../agent-output-validation/)'s
  `repair_once` policy: a `mixed_marker_in_list` finding feeds the
  exact line/column back into the repair prompt.
- Cron-friendly: findings are sorted by `(line, column, kind)`, so
  byte-identical output across runs makes diff-on-the-output a valid
  CI signal.

## Inputs / outputs

```
validate_bullet_markers(text: str) -> list[Finding]

Finding(kind: str, line: int, column: int, raw: str, detail: str)
```

- `text` — the LLM markdown output to scan. Must be `str` (raises
  `ValidationError` otherwise). `line` / `column` are 1-indexed.
- Returns the list of findings sorted by `(line, column, kind)`.
- `format_report(findings)` renders a deterministic plain-text report.

Pure function: no I/O, no markdown parser dependency, no language
model. Fenced code blocks (``` and `~~~`) and thematic breaks (`---`,
`***`) are skipped by the surrounding state machine so a bullet-shaped
line inside a shell transcript never trips the gate. Tabs in
indentation are expanded to 4 spaces before depth comparison.

## Composition

- [`agent-output-validation`](../agent-output-validation/) — feed a
  finding's `line` and `kind` into the repair prompt for a one-turn
  fix.
- [`structured-output-repair-loop`](../structured-output-repair-loop/) —
  the per-attempt validator inside the loop's `validate(attempt)`
  callback; identical-fingerprint repeat findings (same `kind` + same
  `line`) make a stuck loop trivially detectable.
- [`llm-output-quote-style-consistency-validator`](../llm-output-quote-style-consistency-validator/) —
  orthogonal: that template is the consistency gate for quotation
  marks, this is the consistency gate for bullet markers. Both
  emit the same `Finding` shape and stable sort, so a single CI step
  can union their findings.
- [`structured-error-taxonomy`](../structured-error-taxonomy/) —
  classifies as `repair_once / attribution=model` (mechanical fix:
  rewrite the minority marker to the majority).

## Worked example

```
$ python3 example.py
```

Verbatim output:

```
=== 01-clean-dash ===
OK: bullet markers are consistent.

=== 02-mixed-in-single-list ===
FOUND 2 bullet-marker finding(s):
  [inconsistent_indent_marker] line=5 col=1 raw='*' :: indent=0; markers={'*': 1, '-': 3}; majority='-'
  [mixed_marker_in_list] line=5 col=1 raw='*' :: block markers={'*': 1, '-': 3}; majority='-'

=== 03-mixed-across-blocks ===
FOUND 3 bullet-marker finding(s):
  [inconsistent_indent_marker] line=8 col=1 raw='*' :: indent=0; markers={'*': 2, '-': 4}; majority='-'
  [mixed_marker_in_document] line=8 col=1 raw='*' :: document blocks by dominant marker={'*': 1, '-': 2}; majority='-'
  [inconsistent_indent_marker] line=9 col=1 raw='*' :: indent=0; markers={'*': 2, '-': 4}; majority='-'

=== 04-nested-marker-drift ===
FOUND 2 bullet-marker finding(s):
  [inconsistent_indent_marker] line=7 col=3 raw='*' :: indent=2; markers={'*': 1, '-': 3}; majority='-'
  [mixed_marker_in_list] line=7 col=3 raw='*' :: block markers={'*': 1, '-': 5}; majority='-'

=== 05-fenced-code-is-ignored ===
OK: bullet markers are consistent.

=== 06-clean-asterisk ===
OK: bullet markers are consistent.

```

Notes:

- Case 02 catches the lone `*` line as a per-list and per-depth
  minority. The two findings at `line=5 col=1` are intentional: the
  block-level check tells you "this list is mixed", the depth-level
  check tells you "depth 0 across the document is mixed too".
- Case 03 demonstrates the document-level axis. Each individual block
  is internally clean, but the document mixes one `*`-block with two
  `-`-blocks; the offending block is reported once at its first
  bullet, plus the depth-level minority lines.
- Case 04 shows the nested-marker drift case. The outer bullets are
  consistent dashes; one nested `*` at `indent=2` trips both the
  block-level and depth-level checks.
- Case 05 demonstrates fence-skipping: a shell-transcript line
  starting with `-` or `*` inside a ``` block is not counted as a
  bullet, so the surrounding clean dash list passes.
- Case 06 is clean asterisk-only — single-marker documents pass on
  every axis regardless of which marker is chosen.

## Files

- `validator.py` — pure stdlib detector + `format_report`
- `example.py` — six-case worked example
