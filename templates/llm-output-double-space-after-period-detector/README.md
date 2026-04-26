# `llm-output-double-space-after-period-detector`

Pure-stdlib detector for inconsistent or excess spacing after
sentence-ending punctuation in an LLM Markdown / prose output blob —
the artifact class that is invisible in HTML render (every browser
collapses runs of spaces) but real in the source bytes, in `git
diff`, in plain-text terminals, and in any sentence tokenizer that
treats "1 space" vs "2 spaces" as a different gap.

The bug is mixing, not the choice itself. A document that is 100%
one-space passes; a document that is 100% two-space passes; a
document that mixes the two — or stacks 3+ spaces anywhere, or
slips a tab in — fires.

Five finding kinds:

- `mixed_sentence_spacing` — the document contains MORE THAN ONE
  sentence-spacing convention (one-space sentences AND two-space
  sentences both present). Reported once, scope=blob, with the
  per-convention inventory (`one_space=N two_space=N`). The
  summary is emitted ONCE before any per-line minority-spacing
  finding so a reviewer sees the inventory before the per-line
  noise.

- `excess_space_after_period` — a run of 3+ spaces after sentence
  punctuation. Always reported per occurrence with `(line, col,
  run_length)`. A 3+ run is never legitimate sentence spacing in
  any convention; it's either OCR bleed-through or a model that
  lost track of its own style mid-paragraph.

- `two_space_in_one_space_blob` — a two-space gap in a blob whose
  majority is one-space. Reported per occurrence with the line and
  column of the punctuation so the fix is mechanical.

- `one_space_in_two_space_blob` — symmetric: a one-space gap in a
  blob whose majority is two-space. Reported per occurrence.

- `tab_after_period` — a TAB rather than a space after sentence
  punctuation. Always reported regardless of majority. A model
  emitting a literal tab in prose is leaking a Makefile / TSV
  artifact and the bug needs to be fixed before any tooling that
  re-tabifies the doc later.

A "sentence-ending punctuation" is `.` / `!` / `?` followed by `[
\t]+` followed by a capital letter or an opening quote/bracket
(`"`, `'`, `(`, `[`, `A`–`Z`). The capital-letter requirement is
the load-bearing filter that prevents false positives on:

- decimals (`3.14`)
- filenames / URLs (`config.yaml is loaded`)
- abbreviations (`e.g. the next item`, `i.e. that thing`)
- file extensions (`.py files`)

A `.` followed by `[ \t]+` followed by a lowercase word is treated
as NOT a sentence boundary — it's almost certainly an abbreviation
or a continuation. False negatives on legitimate sentences whose
next word is a lowercase brand name (`iPhone`, `iOS`) are a
deliberate trade — false positives on `e.g.` / `i.e.` / `vs.` would
be far noisier.

Pure: input is `str`, no I/O, no third-party deps, no NLP model.

## When to use

- Pre-publish gate on any LLM-generated **commit message body**,
  **PR description**, **issue body**, **release-notes paragraph**
  before `gh` / `git` writes it to a permanent record. A two-space
  sentence that survives is invisible in the GitHub UI render but
  shows up in `git log` / `git format-patch` / plain-text email
  subscribers' clients.
- Pre-flight on an LLM-drafted **runbook** / **status update**
  before paste into Slack: Slack's Markdown renderer collapses
  spaces, but copy-out from Slack preserves them, and the next
  consumer that re-renders the doc in a strict-typography pipeline
  (LaTeX, typesetting QA) will flag every mixed gap.
- Audit step in a **review-loop** that promotes
  [`agent-output-validation`](../agent-output-validation/)'s
  `repair_once` policy: a `mixed_sentence_spacing` finding gives
  the repair prompt a single concrete instruction ("re-emit with
  one space after each sentence-ending period; do not change any
  other byte"). The blob-scope summary's inventory string is small
  and gives the model exactly the signal it needs.
- Cron-friendly: findings are sorted by `(line_number, column,
  kind)` and the report is deterministic, so byte-identical output
  across runs makes diff-on-the-output a valid CI signal.

## Inputs / outputs

```
detect_double_space_after_period(text: str) -> list[Finding]

Finding(kind: str, line_number: int, column: int, detail: str)
```

- `text` — the LLM output to scan. Must be `str` (raises
  `ValidationError` otherwise).
- `Finding.line_number` is 1-based and points at the line
  containing the offending punctuation. `Finding.column` is the
  1-based column of the punctuation byte itself, so a `sed -E`
  fix is keyed off the exact location. The blob-scope
  `mixed_sentence_spacing` summary uses `line_number=0 column=0`
  (rendered `scope=blob`) to mark it as blob-scope.
- `format_report(findings)` renders a deterministic plain-text
  report. Empty list → `"OK: sentence spacing is consistent.\n"`.

Pure function: no I/O, no Markdown parser, no NLP. The detector is
read-only.

## Composition

- [`agent-output-validation`](../agent-output-validation/) — feed a
  `mixed_sentence_spacing` summary into the repair prompt verbatim;
  the `one_space=N two_space=N` inventory tells the model exactly
  what it did wrong.
- [`structured-output-repair-loop`](../structured-output-repair-loop/) —
  the per-attempt validator inside the loop's `validate(attempt)`
  callback. The blob-scope `mixed_sentence_spacing` finding's
  detail string is stable across attempts, so a stuck loop is
  detectable (same inventory two attempts in a row → bail).
- [`llm-output-trailing-whitespace-and-tab-detector`](../llm-output-trailing-whitespace-and-tab-detector/) —
  orthogonal: that template enforces what's BEFORE each line
  ending, this enforces what's AFTER each sentence within a line.
  Both use the same `Finding` shape (with column) and the same
  stable sort, so a single CI step can union their findings.
- [`llm-output-redundant-blank-line-detector`](../llm-output-redundant-blank-line-detector/) —
  orthogonal axis: blank lines between content vs spaces within
  prose. Both flag invisible-in-render byte-level inconsistencies.
- [`llm-output-mixed-line-ending-detector`](../llm-output-mixed-line-ending-detector/) —
  same family of "the bytes the model emitted disagree with the
  bytes the publishing convention expects". Run all four in one
  CI step on every LLM-drafted markdown blob.
- [`structured-error-taxonomy`](../structured-error-taxonomy/) —
  classifies as `do_not_retry / attribution=model` for any of the
  five kinds. Re-running the same call on the same model is
  unlikely to change spacing behaviour without a corrective
  system message.

## Worked example

```
$ python3 example.py
```

Verbatim output:

```
=== 01-clean-one-space ===
input (· = space, → = tab):
  | First·sentence.·Second·sentence.·Third·sentence.
OK: sentence spacing is consistent.

=== 02-clean-two-space ===
input (· = space, → = tab):
  | First·sentence.··Second·sentence.··Third·sentence.
OK: sentence spacing is consistent.

=== 03-mixed-one-and-two-space ===
input (· = space, → = tab):
  | First·sentence.·Second·sentence.··Third·sentence.·Fourth·sentence.
FOUND 2 sentence-spacing finding(s):
  [mixed_sentence_spacing] scope=blob :: blob mixes sentence-spacing conventions: one_space=2 two_space=1
  [two_space_in_one_space_blob] line=1 col=32 :: two-space sentence gap in a one-space-majority blob

=== 04-excess-space-3-plus ===
input (· = space, → = tab):
  | Heading·complete.···Body·begins·here.·Tail·follows.
FOUND 1 sentence-spacing finding(s):
  [excess_space_after_period] line=1 col=17 :: run of 3 spaces after sentence-ending punctuation

=== 05-tab-after-period ===
input (· = space, → = tab):
  | End·of·intro.→Body·starts·now.·Then·more·body.
FOUND 1 sentence-spacing finding(s):
  [tab_after_period] line=1 col=13 :: tab character(s) after sentence-ending punctuation (run length 1)

=== 06-decimals-and-abbrevs-not-flagged ===
input (· = space, → = tab):
  | Pi·is·3.14·and·e.g.·the·next·item·is·fine.·Real·sentence·here.·Another·one.
OK: sentence spacing is consistent.

=== 07-mixed-with-quoted-opener ===
input (· = space, → = tab):
  | First·sentence.·"Quoted·opener"·sentence.··(Bracketed)·sentence.
FOUND 2 sentence-spacing finding(s):
  [mixed_sentence_spacing] scope=blob :: blob mixes sentence-spacing conventions: one_space=1 two_space=1
  [two_space_in_one_space_blob] line=1 col=41 :: two-space sentence gap in a one-space-majority blob

```

Notes:

- Case 01 — three sentences with one space between each. Modern
  publishing convention. Passes silently.
- Case 02 — three sentences with two spaces between each.
  Typewriter convention, but CONSISTENT. The detector flags
  mixing, not the choice itself, so this passes too. If your
  house style is one-space-only, run a separate strict-mode
  validator on top.
- Case 03 — proves the per-occurrence finding. Three boundaries,
  two of them one-space, one of them two-space. Majority is
  one-space (count 2 vs 1) so the two-space gap fires
  `two_space_in_one_space_blob` at the column of the punctuation
  (col 32 — the `.` after "Second sentence"). The blob-scope
  `mixed_sentence_spacing` summary fires once first.
- Case 04 — proves `excess_space_after_period`. A 3-space run is
  never sentence spacing in any convention; reported regardless of
  blob majority. (Note: with only one boundary in the doc, no
  `mixed_sentence_spacing` summary is emitted because there's
  only one CONVENTION boundary; the 3-space run is excluded from
  the convention vote.)
- Case 05 — proves `tab_after_period`. The tab is at column 13
  (the byte position of the `.`). Tab is in the run, so the run
  length is 1 (one tab byte).
- Case 06 — the load-bearing false-positive case. `3.14` is a
  decimal (next char is a digit, not a space — regex doesn't
  match). `e.g.` is followed by space then `the` (lowercase) — the
  capital-letter filter rules it out. `is fine. Real` IS a
  sentence boundary (next char is `R`). All four boundaries are
  one-space. Passes clean.
- Case 07 — proves the opener filter accepts not just A-Z but
  also `"`, `'`, `(`, `[`. The first boundary opens with `"`
  (one-space), the second opens with `(` (two-space). Mixing is
  flagged.

## Files

- `detector.py` — pure-stdlib detector + `format_report`
- `example.py` — seven worked-example cases (run: `python3 example.py`)
- `README.md` — this file

## Limitations

- The detector does NOT inspect the bytes inside fenced code
  blocks specially: a `". X"` pattern inside a ` ``` ` fence is
  reported the same as in prose. In practice this is rarely a
  false positive (sentence-shaped punctuation runs are uncommon
  inside code) but if your doc legitimately ships English prose
  AND a code block whose own internal style differs, scope the
  detector to the prose part externally.
- Sentences that legitimately start with a lowercase brand name
  (`iPhone`, `iOS`, `eBay`) are NOT recognized as sentence
  boundaries and so any spacing inconsistency immediately before
  them is silently passed. The trade is documented above; the
  alternative (matching any non-whitespace) would generate noise
  on every abbreviation.
- Sentences that end with `.")` (period inside closing
  quotes/parens) are not recognized as boundaries — the detector
  expects the punctuation to be the last byte before the
  whitespace. This is a deliberate narrow scope; broadening would
  require a small state machine and is not worth the false
  positives on `("Hello.")` mid-sentence.
- A blob that is exactly the empty string `""` returns `[]` (no
  findings). An empty blob has no spacing to be inconsistent.
- The detector does not attempt to repair anything. Repair is
  trivially `re.sub(r'([.!?])  +([\"\'(\[A-Z])', r'\1 \2', text)`
  (collapse all post-sentence whitespace runs to a single space
  before a capital opener), or lives in
  [`agent-output-validation`](../agent-output-validation/)
  depending on the policy direction (one-space vs two-space).
