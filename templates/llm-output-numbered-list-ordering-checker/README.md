# `llm-output-numbered-list-ordering-checker`

Pure stdlib checker for ordered (numbered) list ordering in an
LLM Markdown output blob — the failure mode where a model writes
`1. 2. 4. 5.` because the third token slipped, and the renderer
dutifully shows "1, 2, 3, 4" because Markdown auto-renumbers, so
the missing item is now invisible in `gh pr view` while the raw
blob in `git log` shows the truth.

Four finding kinds, fence-aware, sub-list-aware:

- `non_monotonic` — a list item's number is <= the previous
  item's number in the same list (`1, 2, 2, 3` OR `1, 3, 2`).
  This is almost always a model duplication error.
- `skipped_number` — a list item's number jumps by more than 1
  in a list that started at 1 (`1, 2, 4, 5` — the `4` is
  reported). Reported only for lists that start at 1; if the
  list starts elsewhere, the `bad_start` finding fires instead
  and skipped-number is suppressed (a single finding per axis).
- `bad_start` — the first item of a list does not start at 1
  (and not at 0, which is sometimes deliberate for tutorial
  counting). Reported once at the first item's line.
- `mixed_separator` — list uses both `1.` and `1)` styles in
  the same list. Some Markdown viewers treat the change as a
  new list and silently restart numbering.

A "list" is a contiguous run of lines whose stripped form
matches `^\d+[.)] +\S`. The list ends at the first non-matching
line (blank, prose, heading, fence, etc.). Indented sub-lists
are tracked independently per indent level — a top-level list
and its 2-space-indented child list are scored separately
(see case 07 in the worked example).

Lines inside a fenced code block (delimited by ``` or ~~~) are
NOT scanned — code samples often have intentional `1. 3.` style
sequences (e.g. quoting bug repro steps). See case 06.

## When to use

- Pre-publish gate on any LLM-generated **commit message body**,
  **PR description**, **issue body**, or **release notes**
  before `gh` / `git` writes it to a permanent record. The
  rendered list looks correct in the preview pane but the raw
  blob carries the wrong numbering forever.
- Pre-flight on **runbooks** and **incident reports** drafted
  by an assistant. A skipped step in a runbook is the worst
  class of doc bug — the operator does the wrong N+1 step
  because the actual N+1 was deleted.
- Audit step in a **review-loop** that promotes
  [`agent-output-validation`](../agent-output-validation/)'s
  `repair_once` policy: a `skipped_number` finding feeds the
  offending line + expected number back into the repair prompt.
- Cron-friendly: findings are sorted by `(line_number, kind)`
  and the report is rendered in a deterministic format, so
  byte-identical output across runs makes diff-on-the-output
  a valid CI signal.

## Inputs / outputs

```
detect_ordering_issues(text: str) -> list[Finding]

Finding(kind: str, line_number: int, column: int, raw: str, detail: str)
```

- `text` — the LLM output to scan. Must be `str` (raises
  `ValidationError` otherwise).
- `Finding.line_number` is 1-based; `Finding.column` is 1-based
  and points at the first digit of the offending item number
  (or, for `mixed_separator`, at the separator character) so a
  reviewer can jump directly to the offending byte.
- `format_report(findings)` renders a deterministic plain-text
  report. Empty list → `"OK: numbered lists are well-ordered.\n"`.

Pure function: no I/O, no Markdown parser. Single forward pass
over the lines tracking fence state and a stack of open lists
keyed by indent.

## Composition

- [`agent-output-validation`](../agent-output-validation/) — feed
  a finding's `(line_number, column, kind)` and the expected
  number into the repair prompt for a one-turn fix.
- [`structured-output-repair-loop`](../structured-output-repair-loop/) —
  the per-attempt validator inside the loop's `validate(attempt)`
  callback; the `(line_number, column, kind)` tuple makes a
  stuck loop detectable (same tuple twice in a row → bail).
- [`llm-output-trailing-whitespace-and-tab-detector`](../llm-output-trailing-whitespace-and-tab-detector/) —
  orthogonal: that template enforces line-ending hygiene, this
  enforces ordered-list integrity. Both use the same `Finding`
  shape and a stable sort, so unioned reports stay diffable.
- [`llm-output-markdown-bullet-marker-consistency-validator`](../llm-output-markdown-bullet-marker-consistency-validator/) —
  orthogonal: that template enforces unordered-list bullet
  consistency, this enforces ordered-list integrity. Same
  `Finding` shape; ideal pair for a single CI step.
- [`structured-error-taxonomy`](../structured-error-taxonomy/) —
  classifies `non_monotonic` and `skipped_number` as
  `retry_with_repair / attribution=model` (the model can usually
  fix it in one turn given the line), and `bad_start` /
  `mixed_separator` as `retry_with_repair / attribution=model`
  with a stricter system message.

## Worked Example Output

```
$ python3 example.py
=== 01-clean ===
input:
  | Steps:
  | 1. install dependencies.
  | 2. run the migration.
  | 3. start the worker.
OK: numbered lists are well-ordered.

=== 02-skipped-number ===
input:
  | Repro:
  | 1. open the editor.
  | 2. paste the snippet.
  | 4. observe the crash.
  | 5. file the bug.
FOUND 1 ordering finding(s):
  [skipped_number] line=4 col=1 :: item number 4 skips from previous item number 2 (line 3); expected 3
    line='4. observe the crash.'

=== 03-non-monotonic ===
input:
  | Plan:
  | 1. write the spec.
  | 2. review with the team.
  | 2. address comments.
  | 3. ship.
FOUND 1 ordering finding(s):
  [non_monotonic] line=4 col=1 :: item number 2 is <= previous item number 2 (line 3)
    line='2. address comments.'

=== 04-bad-start ===
input:
  | Punch list:
  | 3. fix the parser.
  | 4. update the docs.
  | 5. cut the release.
FOUND 1 ordering finding(s):
  [bad_start] line=2 col=1 :: first item of list starts at 3; expected 1 (or 0 for zero-indexed lists)
    line='3. fix the parser.'

=== 05-mixed-separator ===
input:
  | Checklist:
  | 1. lint passes.
  | 2) tests pass.
  | 3. coverage holds.
FOUND 1 ordering finding(s):
  [mixed_separator] line=3 col=2 :: separator ')' differs from list's first separator '.' (line 2)
    line='2) tests pass.'

=== 06-fenced-list-not-scanned ===
input:
  | Inside a code fence the renderer shows raw text:
  | ```
  | 1. one
  | 3. three
  | 5. five
  | ```
  | Outside the fence:
  | 1. real first item.
  | 2. real second item.
OK: numbered lists are well-ordered.

=== 07-nested-list-independent-counts ===
input:
  | Outline:
  | 1. parent A.
  |   1. child A.1.
  |   2. child A.2.
  | 2. parent B.
  |   1. child B.1.
  |   3. child B.2 — skipped 2 here.
FOUND 1 ordering finding(s):
  [skipped_number] line=7 col=3 :: item number 3 skips from previous item number 1 (line 6); expected 2
    line='  3. child B.2 — skipped 2 here.'

=== 08-paragraph-restart ===
input:
  | First batch:
  | 1. alpha.
  | 2. beta.
  | 
  | Some prose between the lists.
  | 
  | Second batch:
  | 1. gamma.
  | 2. delta.
OK: numbered lists are well-ordered.
```

Notes:

- Case 02 — the missing `3.` is invisible in any rendered view
  (Markdown auto-renumbers to 1,2,3,4) but obvious in the raw
  blob. The detector pinpoints the 4-numbered item with the
  expected value `3` so the fix is mechanical.
- Case 03 — duplicate `2.` is `non_monotonic` (not skipped).
  The two axes are mutually exclusive on a single line: a
  number that is <= previous cannot also have skipped, and
  vice versa.
- Case 04 — list that starts at 3 trips `bad_start` once at
  the first item; subsequent items (3, 4, 5) are perfectly
  monotonic-and-non-skipping, so no other findings fire.
  `skipped_number` is suppressed because the list did not
  start at 1.
- Case 05 — separator inconsistency (`.` vs `)`). Some
  renderers (CommonMark-strict) treat `2)` as a new list and
  silently restart numbering at 1, so `1. 2) 3.` renders as
  "1, 1, 1". Caught at the byte that diverges.
- Case 06 — proves the fence-awareness invariant. The list
  inside the fence has obvious gaps (1, 3, 5) but is NOT
  reported; the list outside the fence is clean and also not
  reported. Code samples are not prose.
- Case 07 — proves the indent-aware sub-list invariant. The
  parent list (`1. parent A.`, `2. parent B.`) is clean. The
  first sub-list (`1. child A.1.`, `2. child A.2.`) is clean.
  The second sub-list (`1. child B.1.`, `3. child B.2`) trips
  one `skipped_number` at line 7. Three independent counters,
  one finding.
- Case 08 — proves the paragraph-restart invariant. A blank
  line between two `1.` items closes the first list and opens
  a fresh one. Both lists start at 1, so neither trips
  `bad_start`. This matches every real Markdown renderer.

## Files

- `validator.py` — pure stdlib detector + `format_report`
- `example.py` — eight worked-example cases (run: `python3 example.py`)
- `README.md` — this file

## Limitations

- The detector treats any non-item, non-blank line as a hard
  list-close. A Markdown spec strictly says a continuation line
  (indented to align under the item body) is part of the same
  list item; in practice, models rarely emit those for
  numbered lists, and treating them as list-closers makes the
  detector pessimistic-but-deterministic. False positives in
  this mode look like "list restarts after a continuation
  line" — bump the cap or ignore the finding.
- Lists starting at 0 are accepted as a deliberate zero-indexed
  variant. If you want strict "must start at 1", post-filter
  for `bad_start` findings whose detail mentions `starts at 0`.
- Roman-numeral and lettered lists (`a.`, `i.`) are not
  scanned. Markdown does not natively support them as ordered
  lists; a model emitting them produces an unordered-style
  output and is out of scope for this detector.
- Indent comparison expands tabs to 4 spaces. If you use a
  different tab width convention, deeply-nested lists with
  tab indents may be assigned the wrong parent. Stick to space
  indents (or normalize to spaces before scanning) for fully
  reliable nesting detection.
