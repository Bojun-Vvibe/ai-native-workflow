# `llm-output-emphasis-marker-consistency-validator`

Pure stdlib validator for the LLM Markdown failure mode where the
model mixes `*` and `_` markers for the SAME semantic role inside a
single document — one paragraph uses `*italic*`, another uses
`_italic_`; one bold span is `**bold**`, another is `__bold__`. Both
render identically in most viewers, so the bug is invisible at
preview time. It surfaces when:

- the doc is fed into a renderer that honors only one style (some
  older Pandoc front-ends, several wiki engines),
- a downstream linter (`markdownlint` MD049 / MD050, Prettier with
  `--prose-wrap`) flips half the document on autoformat and the diff
  explodes,
- a RAG chunker keyed on string-equality fingerprints of inline spans
  treats `*x*` and `_x_` as different snippets even though they
  render the same.

Five finding kinds, sorted by `(offset, kind)` for byte-identical
re-runs:

- `mixed_italic_marker` — the document contains BOTH `*x*` (asterisk
  italic) AND `_x_` (underscore italic) spans. Reported once per
  minority span (so a 3-asterisk / 1-underscore document fires once
  on the underscore span) with the explicit count table and the
  majority style so a repair prompt is a single string interpolation
  away (`"normalize italics to <majority>"`).
- `mixed_bold_marker` — same but for bold (`**x**` vs `__x__`).
  Tracked separately because a doc may be consistent on italic and
  inconsistent on bold (or vice versa); a single mixed-marker verdict
  would hide the partial-fix opportunity.
- `bold_in_italic_style` — bold-italic mismatch (`***x***` vs
  `___y___`). Distinct because some renderers interpret triple
  markers differently from doubles.
- `unbalanced_marker` — a line contains an ODD number of standalone
  `*` or `_` markers (after stripping fenced code, inline-code spans,
  and backslash-escapes), strongly indicating an unclosed emphasis
  span. Reported per line with the column of the first stray marker
  for a mechanical fix.
- `intraword_underscore` — `_` used INSIDE a word (e.g. `snake_case`)
  in prose, NOT in a code span. CommonMark does not treat intraword
  underscores as emphasis, but several renderers (Discount, older
  Markdown.pl, Slack-flavor) DO, so a `snake_case` identifier in the
  prose body silently italicizes the middle. The fix is backticks.
  Detected on the post-masked line so legitimate `__bold__` /
  `___bi___` markers do not false-positive.

Fenced code blocks (` ``` ` / `~~~`) are SKIPPED entirely. Inline
code spans (`` `...` ``) are stripped from each line before scanning
(replaced with same-length spaces so column math survives).
Backslash-escaped markers (`\*`, `\_`) are removed before counting.

## When to use

- Pre-publish gate on any LLM-generated Markdown destined for a
  surface that mixes renderers (GitHub for the source, Pandoc for the
  PDF, a static-site generator for the docs site, Slack-equivalent
  for paste). Mixed marker style guarantees at least one of those
  surfaces will render unevenly.
- Pre-flight for an LLM-drafted PR description / release-notes blob:
  reviewers reading on one surface see one set of bold spans, the
  archived copy on another surface sees a different set.
- Audit step in a review-loop that promotes
  [`agent-output-validation`](../agent-output-validation/)'s
  `repair_once` policy: a `mixed_italic_marker` finding feeds the
  offending span back into the repair prompt with one instruction
  ("normalize italics to <majority>").
- Cron-friendly: findings are sorted by `(offset, kind)` and the
  report is rendered deterministically, so byte-identical output
  across runs makes diff-on-the-output a valid CI signal.

## Inputs / outputs

```
detect_emphasis_inconsistency(text: str) -> list[Finding]

Finding(kind, line_number, column, offset, raw, detail)
```

- `text` — the LLM output to scan. Must be `str` (raises
  `ValidationError` otherwise).
- `Finding.line_number` is 1-based; `Finding.column` is 1-based and
  points at the first offending byte; `Finding.offset` is the 0-based
  byte offset in the original text so editor jump-to-byte works.
- `Finding.raw` is the full line (without the trailing newline) so a
  reviewer reading the report does not have to jump to the source.
- `format_report(findings)` renders a deterministic plain-text
  report. Empty list → `"OK: emphasis markers consistent.\n"`.

Pure function: no I/O, no Markdown parser, no language detection.

## Composition

- [`agent-output-validation`](../agent-output-validation/) — feed a
  finding's `(offset, kind)` into the repair prompt for a one-turn
  fix; this template is the validator behind the `repair_once`
  policy for any prose output where typographic uniformity matters.
- [`structured-output-repair-loop`](../structured-output-repair-loop/) —
  the `(offset, kind)` tuple is a stable fingerprint; same tuple
  twice in a row → bail rather than burn another turn.
- [`llm-output-quote-style-consistency-validator`](../llm-output-quote-style-consistency-validator/) —
  orthogonal: that template enforces `"` vs `"` consistency, this
  enforces `*` vs `_` consistency. Both use the same `Finding` shape
  and the same stable sort, so a single CI step can union them.
- [`llm-output-bullet-terminal-punctuation-consistency-validator`](../llm-output-bullet-terminal-punctuation-consistency-validator/) —
  orthogonal: that enforces what terminates each bullet body, this
  enforces what surrounds each emphasis span.
- [`llm-output-trailing-whitespace-and-tab-detector`](../llm-output-trailing-whitespace-and-tab-detector/) —
  orthogonal invisible-byte hygiene; same fence-awareness convention.
- [`structured-error-taxonomy`](../structured-error-taxonomy/) —
  classifies as `do_not_retry / attribution=model` for the four
  consistency kinds (a same-prompt retry will reproduce the
  inconsistency); `unbalanced_marker` may be `retry_once` because it
  is often a `max_tokens`-truncation artifact.

## Worked example

```
$ python3 example.py
```

Verbatim output:

```
=== 01-clean ===
input:
  | Status update:
  | 
  | The deploy is *healthy* and the **canary** is *green*.
  | All **critical** alarms are *quiet*.
OK: emphasis markers consistent.

=== 02-mixed-italic ===
input:
  | Notes:
  | 
  | We saw *spike* at 04:00, *recovery* at 04:15, and *steady* by 05:00.
  | The _alert_ was suppressed correctly.
FOUND 1 emphasis finding(s):
  [mixed_italic_marker] line=4 col=5 off=81 :: italic uses '_' but document majority is asterisk (counts: asterisk=3, underscore=1)
    line='The _alert_ was suppressed correctly.'

=== 03-mixed-bold ===
input:
  | Findings:
  | 
  | **Severity** is high; **owner** is the platform team.
  | The __runbook__ is current and the __escalation__ is clear.
FOUND 2 emphasis finding(s):
  [mixed_bold_marker] line=4 col=5 off=69 :: bold uses '__' but document majority is asterisk (counts: asterisk=2, underscore=2)
    line='The __runbook__ is current and the __escalation__ is clear.'
  [mixed_bold_marker] line=4 col=36 off=100 :: bold uses '__' but document majority is asterisk (counts: asterisk=2, underscore=2)
    line='The __runbook__ is current and the __escalation__ is clear.'

=== 04-unbalanced-asterisk ===
input:
  | Conclusion:
  | 
  | The *root cause was a stale cache and we will deploy a fix today.
FOUND 1 emphasis finding(s):
  [unbalanced_marker] line=3 col=5 off=17 :: odd number of '*' markers on line (1) — unclosed emphasis span
    line='The *root cause was a stale cache and we will deploy a fix today.'

=== 05-intraword-underscore ===
input:
  | Implementation note:
  | 
  | The function snake_case_name reads from the cache.
  | Inside backticks it is fine: `snake_case_name` renders verbatim.
FOUND 2 emphasis finding(s):
  [intraword_underscore] line=3 col=19 off=40 :: intraword underscore at byte 19: 'e_c' — wrap identifier in backticks to avoid Slack-flavor italic
    line='The function snake_case_name reads from the cache.'
  [intraword_underscore] line=3 col=24 off=45 :: intraword underscore at byte 24: 'e_n' — wrap identifier in backticks to avoid Slack-flavor italic
    line='The function snake_case_name reads from the cache.'

=== 06-bold-italic-mismatch ===
input:
  | Highlights:
  | 
  | ***Critical*** path is clear; ***owner*** is acknowledged.
  | ___Optional___ follow-ups are tracked in the ticket.
FOUND 1 emphasis finding(s):
  [bold_in_italic_style] line=4 col=1 off=72 :: bold-italic uses '___' but document majority is asterisk (counts: asterisk=2, underscore=1)
    line='___Optional___ follow-ups are tracked in the ticket.'

```

Notes:

- Case 02 — three `*x*` italic spans + one `_alert_` underscore
  italic. The minority underscore span is flagged once with the
  explicit count table (`asterisk=3, underscore=1`); the majority
  declaration in the detail string is the literal text the repair
  prompt drops in to instruct the model to normalize.
- Case 03 — even split (2 vs 2) on bold. Tie-break defaults to
  asterisk, so the two `__runbook__` / `__escalation__` underscore
  bold spans are flagged as the minority. The intraword detector
  correctly does NOT fire on these spans because they are matched as
  bold pairs and masked out before the intraword pass.
- Case 04 — single unclosed `*` on line 3. `unbalanced_marker` fires
  with the column of the stray asterisk for a `sed`-able fix.
- Case 05 — proves the intraword-underscore detection: `snake_case_name`
  in prose flags TWO intraword underscores (one between
  `snake`/`case`, one between `case`/`name`) so the author wraps the
  identifier in backticks. The same identifier inside `` `...` `` on
  the next line is correctly NOT flagged because inline code is
  stripped before scanning.
- Case 06 — proves the bold-italic axis is tracked separately. Two
  `***Critical*** ***owner***` asterisk bold-italic spans + one
  `___Optional___` underscore bold-italic. The minority underscore
  triple is flagged with the count table. The intraword detector
  correctly does NOT fire because the triple-underscore markers were
  masked first.

## Files

- `validator.py` — pure stdlib detector + `format_report`
- `example.py` — six worked-example cases (run: `python3 example.py`)
- `README.md` — this file

## Limitations

- Tie-break on majority defaults to asterisk. A doc with exactly
  equal counts of both styles will see all underscore spans flagged
  as the minority. Adjust the precedence in `detect_emphasis_inconsistency`
  if your house style prefers underscore.
- The unbalanced-marker detector is per-line, not whole-document.
  An emphasis span that legitimately wraps two lines (rare in
  generated Markdown) will fire `unbalanced_marker` on both lines.
  In practice models do not wrap emphasis spans across line breaks.
- Indented code blocks (the 4-space variant) are NOT special-cased.
  If you need different treatment, fence them with ` ``` `.
- The fence parser does not understand language info strings beyond
  "fence opens with this character"; a fence opened with ` ``` ` and
  closed with `~~~` is treated as never-closed. In practice, models
  do not mix fence chars within a single output.
