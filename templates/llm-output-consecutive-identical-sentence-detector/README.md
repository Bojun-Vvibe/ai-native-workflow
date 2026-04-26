# `llm-output-consecutive-identical-sentence-detector`

Pure stdlib detector for the LLM failure mode where adjacent
sentences are identical or near-identical — the artifact you see
when an instruction-following model loses sampling momentum and
emits the same idea twice in a row, e.g.:

```
The deploy is healthy. The deploy is healthy. We can ship.
```

Three finding kinds:

- `exact_repeat` — two adjacent sentences are byte-identical after
  whitespace normalization. The unambiguous signal that the model
  stuttered.
- `case_repeat` — two adjacent sentences are identical except for
  letter case (e.g. `"Reviewers were notified. reviewers were
  notified."`). Still almost certainly a model artifact: anaphora —
  the rhetorical device of repeating a phrase — repeats the
  *opening* of successive clauses, not the entire sentence; an
  English writer never legitimately closes one sentence with a
  capitalized word and opens the next with the lowercase form of
  the *same complete sentence*.
- `near_repeat` — two adjacent sentences differ by at most
  `near_max_edits` token edits (default 1) AND are at least
  `near_min_tokens` tokens long (default 4). Catches the "same
  sentence with one word swapped" case (`"finished at 04:00 UTC."`
  vs `"finished at 05:00 UTC."`) without flagging trivial fragments
  like `"Yes."` `"No."`.

Block boundaries reset the previous-sentence context so a sentence
legitimately reused across two paragraphs / sections does not flag
(case 05 in the worked example proves it). Block resets fire on:

- a blank line (paragraph break)
- a heading line (`#` … `######`)
- a bullet (`- ` `* ` `+ `) or numbered (`1. ` `1) `) list start
- a blockquote marker (`>`)
- a table row (`|`)

Sentences inside fenced code blocks (` ``` ` / `~~~`) are SKIPPED
entirely — a code comment that legitimately contains `// TODO. //
TODO.` should not flag.

Sentence-internal newlines are collapsed to single spaces before
comparison, so a hard-wrapped paragraph that stutters across the
line wrap (case 06) is still caught.

## When to use

- Pre-publish gate on any LLM-generated **status report**, **PR
  description**, **postmortem narrative**, or **release note**
  before it lands in a permanent record. Stutter is the artifact
  reviewers always notice second and never bother to file a bug
  for, but it makes the doc look unedited.
- Post-generation hook on a **streaming agent reply** before the
  final flush — adjacent-sentence stutter is the most common
  failure mode of `temperature=0` decoding under a long context, and
  the cheapest one to detect from the produced bytes alone.
- Audit step in a **review-loop** that promotes
  [`agent-output-validation`](../agent-output-validation/)'s
  `repair_once` policy: a `near_repeat` finding feeds both
  sentences back into the repair prompt with a single instruction
  ("collapse these two adjacent sentences into one").
- Cron-friendly: findings are sorted by `(offset, kind)`, the
  `Finding` shape carries both sentences verbatim, and the rendered
  report is byte-identical across runs — diff-on-the-output is a
  valid CI signal.

## Inputs / outputs

```
detect_stutter(
    text: str,
    *,
    near_max_edits: int = 1,
    near_min_tokens: int = 4,
) -> list[Finding]

Finding(kind: str, offset: int, sentence_a: str, sentence_b: str, detail: str)
```

- `text` — the LLM output to scan. Must be `str` (raises
  `ValidationError` otherwise).
- `near_max_edits` — token-level Levenshtein cap for `near_repeat`.
  Default 1. Set higher (2 or 3) for noisier model output where the
  stutter is partially paraphrased; the cost is only the additional
  DP rows on near-length sentences. `0` disables `near_repeat`.
- `near_min_tokens` — minimum tokens in BOTH sentences for
  `near_repeat` to apply. Default 4. Prevents trivial-fragment
  false positives (`"Yes."` `"No."` differ by 1 token edit but are
  not stutter).
- `Finding.offset` is the 0-based byte offset of the **second**
  sentence in the original text. The first sentence's location is
  immediately before; the report carries both bodies verbatim so
  the reviewer never has to jump back to the source.
- `format_report(findings)` renders a deterministic plain-text
  report. Empty list → `"OK: no consecutive-identical-sentence
  stutter detected.\n"`.

Pure function: no I/O, no NLP library, no model loading. The
detector tokenizes with a single `re.findall(r"[A-Za-z0-9]+", …)`
and runs an early-exit Levenshtein bounded by `near_max_edits + 1`
so cost stays linear in input size for typical model output.

## Composition

- [`agent-output-validation`](../agent-output-validation/) — feed a
  finding's `(sentence_a, sentence_b, kind)` into the repair prompt
  for a one-turn fix; this template is the validator behind the
  `repair_once` policy for prose outputs that may stutter.
- [`structured-output-repair-loop`](../structured-output-repair-loop/) —
  the per-attempt validator inside the loop's `validate(attempt)`
  callback. The `(offset, kind, sentence_a)` tuple is a stable
  fingerprint: same tuple twice in a row means the repair turn did
  not change the offending pair, so the loop should `bail` on
  `stuck` rather than burn another turn.
- [`llm-output-bullet-terminal-punctuation-consistency-validator`](../llm-output-bullet-terminal-punctuation-consistency-validator/) —
  orthogonal: that template enforces consistency *within* a bullet
  list, this enforces non-stutter *within* a paragraph. Same
  `Finding` shape and stable sort, so a single CI step can union
  their findings.
- [`llm-output-quote-style-consistency-validator`](../llm-output-quote-style-consistency-validator/) —
  orthogonal: that one is about typographic consistency, this is
  about content non-repetition. Both use deterministic per-offset
  sort so unioned reports stay diffable.
- [`structured-error-taxonomy`](../structured-error-taxonomy/) —
  classifies as `do_not_retry / attribution=model` for any of the
  three kinds. Stutter is a sampling artifact; retrying the same
  call against the same model with the same seed will reproduce it
  and a corrective system message is the right fix.

## Worked example

```
$ python3 example.py
```

Verbatim output:

```
=== 01-clean ===
input:
  | The deploy is healthy. We can ship the change.
OK: no consecutive-identical-sentence stutter detected.

=== 02-exact-repeat ===
input:
  | The deploy is healthy. The deploy is healthy. We can ship.
FOUND 1 stutter finding(s):
  [exact_repeat] offset=23 :: two adjacent sentences are byte-identical
    a='The deploy is healthy.'
    b='The deploy is healthy.'

=== 03-case-repeat ===
input:
  | Reviewers were notified. reviewers were notified. Merge cleared.
FOUND 1 stutter finding(s):
  [case_repeat] offset=25 :: two adjacent sentences differ only in letter case
    a='Reviewers were notified.'
    b='reviewers were notified.'

=== 04-near-repeat ===
input:
  | The migration finished at 04:00 UTC. The migration finished at 05:00 UTC.
FOUND 1 stutter finding(s):
  [near_repeat] offset=37 :: two adjacent sentences differ by 1 token edit(s); len_a=7 tokens, len_b=7 tokens
    a='The migration finished at 04:00 UTC.'
    b='The migration finished at 05:00 UTC.'

=== 05-paragraph-resets-context ===
input:
  | Section 1: incident summary.
  | 
  | The deploy is healthy.
  | 
  | Section 2: follow-up.
  | 
  | The deploy is healthy.
OK: no consecutive-identical-sentence stutter detected.

=== 06-hard-wrapped-stutter ===
input:
  | The on-call engineer paged the team and started
  | the runbook. The on-call engineer paged the team
  | and started the runbook. The incident was resolved.
FOUND 1 stutter finding(s):
  [exact_repeat] offset=61 :: two adjacent sentences are byte-identical
    a='The on-call engineer paged the team and started the runbook.'
    b='The on-call engineer paged the team and started the runbook.'

```

Notes:

- Case 02 — the two `"The deploy is healthy."` sentences are
  byte-identical and adjacent. The report carries both verbatim,
  not just an offset, so a reviewer reading the report alone has
  enough to fix the prompt.
- Case 03 — the second sentence opens with a lowercase `r`. The
  detector rules out `exact_repeat`, then the lowercased form
  matches, so it fires `case_repeat`. Real anaphora repeats the
  *opening words* across successive clauses, not the entire
  sentence in a different case, so this is reliably an artifact.
- Case 04 — the only differing token is `04` vs `05`. Both
  sentences are 7 tokens (above the `near_min_tokens=4` floor) and
  the edit distance is exactly 1 (at the `near_max_edits=1` cap), so
  `near_repeat` fires. The report includes both lengths and the
  edit count so a reviewer can decide whether the model meant to
  emit two distinct facts or stuttered.
- Case 05 — the same sentence (`"The deploy is healthy."`) appears
  in two different sections separated by a heading-like line and a
  blank line. Block boundaries reset the previous-sentence context,
  so this is correctly NOT flagged. Without the block-reset rule,
  any document with a repeated heading-pattern would false-positive
  on every section start.
- Case 06 — the input is hard-wrapped across three lines. After
  whitespace normalization, both copies of `"The on-call engineer
  paged the team and started the runbook."` collapse to the same
  61-char string and `exact_repeat` fires. The offset (61) points
  at the second sentence's first byte in the *original* text (not
  the normalized form), so editor jump-to-line works.

## Files

- `validator.py` — pure stdlib detector + `format_report`
- `example.py` — six worked-example cases (run: `python3 example.py`)
- `README.md` — this file

## Tuning

- For an aggressive gate on agent **chat replies** (where the user
  reads every word), use the defaults — they catch all three kinds
  with no tuning.
- For a permissive gate on agent **research notes** (where some
  near-repetition is unavoidable because the model is summarizing
  multiple sources that say nearly the same thing), set
  `near_max_edits=0` to keep only `exact_repeat` and `case_repeat`.
- For a stricter gate on **legal / contract-style** drafts (where
  near-repetition with one swapped word is often a copy-paste bug
  with serious downstream consequences), raise `near_max_edits=2`
  and lower `near_min_tokens=3`.

## Limitations

- Sentence segmentation is intentionally cheap (terminator + space).
  A document full of decimal numbers or abbreviations like
  `"Mr. Smith"` will under-segment, but that conservatively reduces
  false positives — the detector will only fire when two
  *adjacent-after-our-segmentation* spans match.
- The detector compares **adjacent** sentences only. A sentence
  that repeats two paragraphs later is not flagged; that's a
  different bug (full-document near-duplicate detection) and
  belongs in a separate template.
- Token equality is case-insensitive and punctuation-stripped, so
  `"healthy."` and `"healthy"` count as the same token for the
  `near_repeat` edit-distance computation. This is intentional:
  a sentence ending differing only in the terminator is already
  caught (or correctly not caught) by the `exact_repeat` and
  `case_repeat` rules above.
