# llm-output-sentence-initial-capitalization-checker

Pure-stdlib detector for sentences in LLM-generated Markdown prose
that start with a lowercase letter. This is the highest-volume LLM
output cleanup chore there is: the model emits a list, finishes the
list, then resumes prose with a lowercased connector ("then we
publish..."), or follows a fenced code block with "this prints...".
The Markdown renders cleanly. A copy editor flags it.

## Why this exists

LLM stylesheets routinely require sentence-case prose. Failures
cluster in three predictable shapes:

- **List-tail spillover.** The model writes a list of imperative
  fragments ("collect the inputs", "run the validator") and then
  the next paragraph starts with "then we publish the report" —
  carried over from the list rhythm.
- **Post-fence resumption.** After a fenced code block the next
  sentence often starts "this command...", "the output above...",
  "note that..." — the model treats the fence boundary as a
  continuation rather than a hard restart.
- **Mid-document drift.** In long outputs the model's casing
  discipline degrades; sentences ten paragraphs deep are more
  likely to start lowercased than sentences in paragraph one.

This detector is a fast, deterministic gate for all three.

## What is and is not flagged

| Context | Behavior |
|---|---|
| Sentence in a normal paragraph starting with a lowercase letter | **Flagged** |
| First word is on the curated allowlist (`rsync`, `iPhone`, `macOS`, `git`, …) | Not flagged |
| Inside a fenced code block | Not flagged |
| Inside inline `code` runs | Not flagged (stripped before splitting) |
| Markdown headings (`#`, `##`, …) | Not flagged (headings have their own casing rules) |
| List item body — each item is treated as its own paragraph | **Flagged** if the item's first sentence starts lowercased |
| URL inside `[text](url)` | Not flagged (URL portion is masked) |

The allowlist is intentionally short and curated; it covers
well-known intentionally-lowercase identifiers (Apple product names,
common Unix utilities, common protocol prefixes). Extend it for your
domain if you have a stable vocabulary of lowercase-first names.

## API

```python
from validator import detect_lowercase_sentence_starts, format_report

findings = detect_lowercase_sentence_starts(text)
print(format_report(findings))
```

Each `Finding` carries `line_no`, `column`, `first_word`, and
`sentence_preview`. Findings are sorted by `(line_no, column)` so
byte-identical re-runs make diff-on-the-output a valid CI signal.

## Worked example

`example.py` exercises eight cases. Run it directly:

```
python3 example.py
```

Captured output (verbatim):

```
=== case 01 clean prose, three sentences ===
OK: every sentence starts with an uppercase letter (or an allowlisted identifier).

=== case 02 lowercased sentence after a list ===
FOUND 3 lowercase sentence start(s):
  line 3 col 1: first_word='collect' sentence='collect the inputs'
  line 4 col 1: first_word='run' sentence='run the validator'
  line 6 col 1: first_word='then' sentence='then we publish the report.'

=== case 03 lowercased sentence after a code fence ===
FOUND 1 lowercase sentence start(s):
  line 7 col 1: first_word='this' sentence='this prints the report to stdout.'

=== case 04 allowlisted identifier (rsync) starting a sentence ===
OK: every sentence starts with an uppercase letter (or an allowlisted identifier).

=== case 05 allowlisted identifier (iPhone) starting a sentence ===
OK: every sentence starts with an uppercase letter (or an allowlisted identifier).

=== case 06 inline code does not count as the sentence start ===
FOUND 1 lowercase sentence start(s):
  line 1 col 9: first_word='initializes' sentence='initializes the counter.'

=== case 07 multiple lowercase starts in one paragraph ===
FOUND 3 lowercase sentence start(s):
  line 1 col 1: first_word='the' sentence='the run failed.'
  line 1 col 17: first_word='it' sentence='it then retried.'
  line 1 col 34: first_word='it' sentence='it failed again.'

=== case 08 heading is not flagged even if lowercased ===
OK: every sentence starts with an uppercase letter (or an allowlisted identifier).

```

What the cases prove:

- **01** clean sentence-case prose passes silently. No false
  positives on the most common LLM output shape.
- **02** the list-tail spillover case fires three findings — one
  per imperative list item plus the post-list paragraph. List items
  are deliberately treated as their own paragraphs because copy
  editors usually want the first word of each list item capitalized
  too; if your style guide allows lowercase list items, downgrade
  list-item findings to warnings rather than weakening the
  detector.
- **03** the post-fence "this prints..." case is correctly flagged
  on the line after the closing fence — the highest-leverage
  failure shape for technical writing.
- **04 / 05** the allowlist suppresses `rsync` and `iPhone` —
  legitimate sentence starts that a naive case check would flag.
- **06** an inline-code-only opener (`` `x = 1` initializes... ``)
  has its inline code masked, so the detector sees the next word
  ("initializes") as the sentence start. This is intentional: a
  sentence that opens with a bare expression and then continues
  with lowercase prose almost always *should* be capitalized
  ("This initializes the counter"). If your style guide tolerates
  this shape, allowlist the offending first word or rewrite the
  sentence.
- **07** three lowercase starts in one line are each flagged
  separately with correct column offsets, so a `sed` or
  `String.fromCharCode` patch can target them precisely.
- **08** a Markdown heading line is never flagged even when its
  text is lowercase. Headings have their own casing conventions
  and live outside this gate.

## Composition

- **`llm-output-acronym-first-use-expansion-checker`** — orthogonal
  prose-hygiene axis (acronym expansion vs sentence-initial casing).
  Same `Finding` shape, so a single CI step can union both.
- **`llm-output-emphasis-marker-consistency-validator`** and the
  rest of the Markdown-hygiene family — same fence- and
  heading-awareness convention, so the column offsets reported here
  align with theirs.
- **`agent-output-validation`** — feed `(line_no, column,
  first_word)` back into a repair prompt: "capitalize the word
  `then` at line 6 column 1." One-turn fix.

## Tuning

- **Allowlist.** The default list is short and Anglo-Unix-centric.
  Extend `_LOWERCASE_FIRST_ALLOWLIST` in `validator.py` for your
  domain — product names, library names, CLI tools.
- **List-item policy.** If your style guide allows lowercase list
  items, post-process the report to drop findings whose `line_no`
  matches a `[-*+]` or `1.` line in the source. The detector
  deliberately stays strict by default because list-tail spillover
  (the bug class motivating this template) only surfaces when
  list-item casing is enforced too.
- **Heading exclusion.** Headings are unconditionally skipped. If
  you also want to gate heading casing, run a separate detector
  scoped to heading lines — keep the two concerns orthogonal.
