# `llm-output-markdown-ordered-list-numbering-monotonicity-validator`

Pure stdlib validator for the LLM failure mode where an ordered list
in generated markdown has broken numbering — `1.` `2.` `4.` (skipped
3), or `1.` `2.` `2.` `3.` (duplicate from a copy-paste), or `3.` `4.`
`5.` (started in the middle), or `1.` `2)` `3.` (mixed `.` and `)`
markers in a single block).

The doc renders OK in most viewers — GitHub silently re-numbers an
ordered list to `1, 2, 3` regardless of the source numbers — so the
bug is invisible at preview time. It surfaces later in three places:

- The raw markdown gets pasted into a tracker / wiki / chat that
  honors the source numbers verbatim, and the reader sees `1, 2, 4`.
- A downstream pipeline (TOC generator, RAG chunker keyed on list
  index, citation extractor that returns `step 4 says…`) reads the
  source numbers, not the rendered ones, and silently mis-bucks.
- A reviewer scrolling the diff sees `1.` `2.` `4.` and flags the PR
  on the *count*, not on the actual content the LLM was asked to
  produce.

Four finding kinds, all per-block:

- `non_monotonic` — numbers do not strictly increase by `+1` within
  the block (`1.` `2.` `4.`, or `1.` `3.` `2.`). The most common
  failure mode of `temperature>0` generation that re-counts mid-list.
- `bad_start` — the block opens at something other than `1`. Often
  the signature of a partial generation that lost the head of the
  list.
- `mixed_marker` — one block mixes `.` and `)` markers. Renderers
  handle this inconsistently; the LLM almost certainly meant one or
  the other.
- `duplicate_index` — the same number twice in one block (`1.` `2.`
  `2.` `3.`). Promoted to its own kind because it is the unmistakable
  fingerprint of a copy-paste, not a counting bug.

A "block" terminates on a blank line, a non-list line at the same-or-
shallower indent, end of input, or a fenced-code-block opener. Lines
inside ` ``` ` / `~~~` blocks are SKIPPED entirely so a code sample
with intentionally weird numbers does not flag (case 07 proves this).

Nested ordered lists are tracked independently per indent column —
case 06 in the worked example proves that two outer items each with
their own inner list both restart at `1` correctly.

## When to use

- Pre-publish gate on any LLM-generated **runbook**, **how-to**, or
  **PR description** that contains numbered steps. Off-by-one in a
  step list is the kind of bug a reader believes — they will skip
  step 3 because the source says step 4 comes next.
- Post-generation hook on **agent-authored documentation** before it
  lands in a permanent knowledge base. RAG chunkers that key on list
  index will mis-attribute under broken numbering.
- Audit step in a **review-loop** that promotes
  [`agent-output-validation`](../agent-output-validation/)'s
  `repair_once` policy: a `non_monotonic` or `duplicate_index`
  finding feeds the offending block back into the repair prompt with
  one instruction (`"renumber this list 1..N"`).
- Cron-friendly: findings are sorted by `(line_no, kind, indent)`,
  the report is byte-identical across runs, diff-on-the-output is a
  valid CI signal.

## Inputs / outputs

```
validate_ordered_list_numbering(text: str) -> list[Finding]

Finding(kind: str, line_no: int, indent: int, detail: str, sample: str)
```

- `text` — the markdown to scan. Must be `str` (raises
  `ValidationError` otherwise).
- `Finding.line_no` is 1-based and points at the offending line in
  the source markdown.
- `Finding.indent` is the leading-space count of the line (tabs
  expanded at 4-column tab stops, CommonMark default).
- `Finding.sample` is the offending line verbatim (trailing newline
  stripped) so the report is self-contained — a reviewer reading the
  report alone has enough to fix the prompt.
- `format_report(findings)` renders a deterministic plain-text
  report. Empty list → `"OK: ordered-list numbering is monotonic.\n"`.

Pure function: no I/O, no markdown library, no regex backtracking
hazards. The only state is a tiny stack of `(indent, expected_next,
marker, items_seen)` frames, one per active nesting level.

## Composition

- [`agent-output-validation`](../agent-output-validation/) — feed a
  finding's `(kind, sample)` into the repair prompt for a one-turn
  fix; this template is the validator behind the `repair_once` policy
  for prose outputs that contain numbered lists.
- [`llm-output-markdown-heading-level-skip-detector`](../llm-output-markdown-heading-level-skip-detector/) —
  orthogonal: that template enforces structural correctness of the
  heading tree, this enforces structural correctness of ordered
  lists. Same `Finding`-shape pattern and stable sort, so a single CI
  step can union their findings.
- [`llm-output-fence-extractor`](../llm-output-fence-extractor/) —
  this template's fence-awareness is independently re-implemented
  here for zero-import simplicity, but for projects already using the
  extractor the two compose: extract first, validate the non-fence
  spans.
- [`structured-error-taxonomy`](../structured-error-taxonomy/) —
  classifies all four kinds as `do_not_retry / attribution=model`.
  Renumbering is mechanical; a corrective system message
  (`"emit ordered lists starting at 1 with consecutive integers"`)
  is the right fix and a plain retry will reproduce the bug.
- [`structured-output-repair-loop`](../structured-output-repair-loop/) —
  the per-attempt validator inside the loop's `validate(attempt)`
  callback. The `(line_no, kind)` tuple is a stable fingerprint:
  same tuple twice means the repair turn did not fix the list, so
  the loop should `bail` on `stuck` rather than burn another turn.

## Worked example

```
$ python3 example.py
```

Verbatim output:

```
=== 01-clean ===
input:
  | 1. first
  | 2. second
  | 3. third
OK: ordered-list numbering is monotonic.

=== 02-non-monotonic-skip ===
input:
  | 1. first
  | 2. second
  | 4. fourth
FOUND 1 numbering finding(s):
  [non_monotonic] line=3 indent=0 :: expected 3. got 4.
    | 4. fourth

=== 03-bad-start ===
input:
  | 3. starts at three
  | 4. continues
  | 5. continues
FOUND 1 numbering finding(s):
  [bad_start] line=1 indent=0 :: ordered list opens at 3. but should open at 1
    | 3. starts at three

=== 04-mixed-marker ===
input:
  | 1. dot marker
  | 2) paren marker mixed in
  | 3. dot again
FOUND 1 numbering finding(s):
  [mixed_marker] line=2 indent=0 :: item uses ')' but block opened with '.' at line 1
    | 2) paren marker mixed in

=== 05-duplicate-index ===
input:
  | 1. one
  | 2. two
  | 2. two again (copy-paste)
  | 3. three
FOUND 1 numbering finding(s):
  [duplicate_index] line=3 indent=0 :: index 2 already used in this block
    | 2. two again (copy-paste)

=== 06-nested-clean ===
input:
  | 1. outer one
  |    1. inner one-a
  |    2. inner one-b
  | 2. outer two
  |    1. inner two-a
OK: ordered-list numbering is monotonic.

=== 07-fence-aware ===
input:
  | Real list:
  | 
  | 1. one
  | 2. two
  | 3. three
  | 
  | Code sample (numbers inside fence are NOT validated):
  | 
  | ```python
  | 1. one
  | 2. two
  | 4. four   # intentional in the example
  | ```
OK: ordered-list numbering is monotonic.

```

Notes:

- Case 02 — block opens at `1.` correctly, then `2.`, then jumps
  straight to `4.`. The expected next was `3.` so `non_monotonic`
  fires on line 3 with both the expected and actual numbers in the
  detail string.
- Case 03 — block opens at `3.` instead of `1.`. `bad_start` fires
  on line 1. The validator then resyncs `expected_next=4` so the
  rest of the (correctly +1-incrementing) block does not also
  flag — one finding per cause is the catalog rule.
- Case 04 — line 2 uses `)` while the block opened with `.`. Marker
  mismatch fires on line 2; line 3 correctly switches back to `.`
  and validates clean against the original `.` block. The detail
  string carries the line number where the block opened so a
  reviewer can navigate to the source of truth.
- Case 05 — `2.` appears twice in a row. `duplicate_index` is a
  separate finding kind (not `non_monotonic`) because the fix is
  different: a duplicate is a copy-paste, a non-monotonic skip is a
  counting bug. Different remediation prompts.
- Case 06 — two outer items, each opening its own nested ordered
  list at `1.`. The validator's per-indent stack correctly treats
  the two inner blocks as independent, so both restart at `1`
  without flagging `bad_start`. This is what makes the validator
  safe to run on real-world docs that use nested numbered lists.
- Case 07 — the real list (lines 3-5) validates clean. The fenced
  Python block with intentionally-wrong numbers is correctly
  ignored — `1, 2, 4` inside the fence is sample code, not a list
  the validator owns.

## Files

- `validator.py` — pure stdlib detector + `format_report`
- `example.py` — seven worked-example cases (run: `python3 example.py`)
- `README.md` — this file

## Tuning

The default rules are deliberately strict because every kind has
exactly one mechanical fix: renumber from 1 with `+1` increments and
a single marker. There are no parameters to tune. If a project has
legitimate non-monotonic lists (e.g. literal CVE numbers or step
numbers from an external playbook), wrap those in a fenced code
block — the fence-aware skip is the supported escape hatch.

## Limitations

- Recognizes only the ATX-style ordered-list form (`1.` / `1)`
  followed by a space). Roman numerals (`i.` `ii.`) and lettered
  lists (`a.` `b.`) are intentionally not parsed — they are not
  CommonMark ordered lists, and CommonMark renderers do not honor
  their numbering.
- A bare `1.` with no body and no trailing space is intentionally
  NOT a list item (CommonMark agrees), so a value like `1.5` in a
  paragraph does not start a one-item list.
- A list item with a wrapped second line at deeper indent is
  treated as a continuation of the same item, not a new list. A
  truly indented sub-list (one full indent step deeper) opens a
  fresh nested block, as in case 06.
- The validator works line-by-line. A list whose items contain
  multi-line embedded blocks (lazy continuation, blockquotes inside
  items) is supported only insofar as those continuation lines have
  no leading digit-then-marker sequence; the catalog rule is "real
  ordered-list items start at column = block.indent with the
  number-marker-space form", and any other shape is treated as
  non-list content for the purposes of monotonicity.
