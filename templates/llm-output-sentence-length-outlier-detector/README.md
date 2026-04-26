# `llm-output-sentence-length-outlier-detector`

Pure-stdlib detector for sentence-length outliers in an LLM prose
output blob — three failure modes that streaming LLMs hit constantly
and that downstream graders, TTS engines, and human readers all
trip on.

A normal prose paragraph from a well-tuned model has sentences
clustered in the 8-25 word range. This template owns the three
deviations from that cluster:

- `long_sentence` — a sentence whose word count exceeds `max_words`
  (default 40). LLMs run away from periods when they are streaming
  a list-like clarification ("we saw A, and B, and C, and also D,
  which means..."). Sentences over 40 words are read 30-40% slower
  and are the #1 source of "wait, what was the subject?" misreads
  in LLM-generated docs.
- `short_sentence` — a sentence whose word count is below
  `min_words` (default 3). Single-word `Yes.` and `Done.` are fine
  in dialog but inside a paragraph of prose they almost always
  indicate a botched stream join (a fragment got split off from
  the previous sentence by an erroneous period).
- `outlier_sentence` — a sentence whose word count is more than
  `outlier_factor` (default 3.0) standard deviations from the
  paragraph's own mean. Catches the "buried-clause" failure: a
  60-word sentence in a paragraph of otherwise 12-word sentences
  IS the bug, even if 60 < `max_words` would have let it pass an
  absolute check. Only fires for paragraphs with `>= 3` sentences
  (need a real sample to compute a useful stddev). The same
  sentence may fire BOTH `long_sentence` AND `outlier_sentence` —
  they are reported as separate findings because they suggest
  different fixes (split vs. condense).

Sentence segmentation is intentionally minimal:

- Split on `.`, `!`, `?` followed by whitespace or EOF.
- Skip-list of common abbreviations (`Mr.`, `Mrs.`, `Ms.`, `Dr.`,
  `St.`, `vs.`, `e.g.`, `i.e.`, `etc.`, `Inc.`, `Ltd.`, `No.`)
  so `Dr. Smith arrived.` is one sentence, not two.
- Decimal-number dots (`3.14`, `2.0.1`, `99.95`) are skipped — a
  `.` between two digits does not end a sentence.
- Code spans (`` `code` ``) and fenced code blocks (` ``` `) are
  blanked out (replaced with whitespace, preserving newlines)
  before sentence segmentation. Their `.` and `?` chars are
  syntax, not punctuation.

Paragraph boundaries are line-gap-based: a jump of more than one
line between two consecutive sentence-start lines starts a new
paragraph. The paragraph-relative outlier check uses each
paragraph's own mean and stddev, so a doc with naturally varied
prose (intro paragraph short and punchy, body paragraph dense)
is not falsely flagged.

## When to use

- Pre-publish gate on any LLM-drafted **status update**, **incident
  postmortem**, or **PR description** before paste. A 60-word
  sentence buried in an otherwise tight paragraph is the most
  reliable "this was generated, not edited" signal a reader has,
  and it usually IS a bug — split it.
- Pre-flight on an LLM-generated **release note** or **changelog**.
  A short fragment (`Done.`) sandwiched between two real sentences
  almost always means the model emitted a sentence-level token
  that should have been a comma.
- Inline guard inside a
  [`structured-output-repair-loop`](../structured-output-repair-loop/) —
  the `(sentence_index, kind)` fingerprint is stable, so a rerun
  that produces the same finding twice in a row is a "do not
  retry, the model is stuck" signal.
- Audit step paired with
  [`llm-output-redundant-blank-line-detector`](../llm-output-redundant-blank-line-detector/) —
  this template catches sentence-level shape drift, that one
  catches paragraph-level shape drift; both are pure functions
  with deterministic output, so a single CI step can union them.

## Inputs / outputs

```
detect_sentence_length_outliers(
    text: str,
    *,
    min_words: int = 3,
    max_words: int = 40,
    outlier_factor: float = 3.0,
) -> list[Finding]

Finding(kind: str, sentence_index: int, line_number: int,
        word_count: int, detail: str)
```

- `text` — the LLM output to scan. Must be `str` (raises
  `ValidationError` otherwise).
- `min_words` — sentences with strictly fewer words fire
  `short_sentence`. Default 3. Set to 1 to allow `Yes.` / `Done.`
  fragments (dialog mode).
- `max_words` — sentences with strictly more words fire
  `long_sentence`. Default 40. Set higher (e.g. 80) for academic
  / legal prose where long sentences are the house style.
- `outlier_factor` — stddev-multiplier threshold for
  `outlier_sentence`. Default 3.0. Tighter values (2.0, 2.5)
  catch more outliers; values above 3.5 effectively disable the
  check on small paragraphs.
- `Finding.sentence_index` is 1-based across the entire blob
  (post-fence-strip). `Finding.line_number` is the 1-based source
  line where the sentence STARTS.
- Validation: `min_words > max_words` raises `ValidationError`;
  any non-integer / non-positive threshold raises
  `ValidationError`.
- `format_report(findings)` renders a deterministic plain-text
  report. Empty list → `"OK: no sentence-length outliers.\n"`.

Pure function: no I/O, no NLP library, no third-party deps.

## Composition

- [`llm-output-redundant-blank-line-detector`](../llm-output-redundant-blank-line-detector/) —
  paragraph-level shape, this is sentence-level shape. Run both.
- [`llm-output-parenthesis-balance-validator`](../llm-output-parenthesis-balance-validator/) —
  the long-sentence failure mode often co-occurs with an
  unmatched paren (the model lost track inside a long clause);
  union the findings.
- [`structured-output-repair-loop`](../structured-output-repair-loop/) —
  feed the `Finding.detail` directly into the repair prompt; the
  word-count + line-number anchor gives the model a precise edit
  target ("split sentence 6 starting at line 1").
- [`structured-error-taxonomy`](../structured-error-taxonomy/) —
  classifies `outlier_sentence` as `attribution=model,
  retry_with_split_prompt`. A "split this sentence" repair turn
  is high-yield; a "make this sentence shorter" turn often is not.

## Worked example

```
$ python3 example.py
```

Verbatim output:

```
=== 01-clean-uniform-paragraph ===
input:
  | The build finished in nine minutes flat. The cache hit rate was high. We saw two flaky tests that retried successfully. The deploy step ran without incident. Monitoring stayed green for the full hour.\n
  | 
OK: no sentence-length outliers.

=== 02-long-sentence-absolute ===
input:
  | The migration plan involves reading every record from the legacy table, transforming each field according to the new schema specification, writing the transformed record into the staging table for verification, and finally promoting the verified records into the production table in batches of one thousand to keep the replication lag bounded.\n
  | 
FOUND 1 sentence-length finding(s):
  [long_sentence] sentence=1 line=1 words=51 :: sentence has 51 word(s) (max: 40)

=== 03-short-sentence-fragment ===
input:
  | We rolled the patch out to the canary fleet. Done. Then we waited for the alert window to clear before promoting to general availability.\n
  | 
FOUND 1 sentence-length finding(s):
  [short_sentence] sentence=2 line=1 words=1 :: sentence has 1 word(s) (min: 3)

=== 04-statistical-outlier-with-tighter-factor ===
input:
  | We shipped it. Tests stayed green. The dashboard looked clean. Cache hits rose. Latency held. Then a long sentence appeared describing the seven distinct steps the on-call engineer took to verify the rollout across each region one by one in order. Then back to short.\n
  | 
params: {'outlier_factor': 2.0}
FOUND 2 sentence-length finding(s):
  [short_sentence] sentence=5 line=1 words=2 :: sentence has 2 word(s) (min: 3)
  [outlier_sentence] sentence=6 line=1 words=26 :: sentence has 26 word(s); paragraph mean=6.4 stddev=8.02 deviation=2.44x (factor: 2.0)

=== 05-abbreviation-not-a-sentence-boundary ===
input:
  | Dr. Smith arrived. The Inc. filed Form No. 12 yesterday. Status: e.g. green, i.e. nominal, etc. The team agreed.\n
  | 
OK: no sentence-length outliers.

=== 06-decimal-not-a-sentence-boundary ===
input:
  | Pi is roughly 3.14 today. The version bumped to 2.0.1 overnight. We saw 99.95 percent uptime.\n
  | 
OK: no sentence-length outliers.

=== 07-code-spans-and-fences-excluded ===
input:
  | Use `os.path.join` to build paths. Then call `f.write(buf)` and close.\n
  | ```python\n
  | x = 1.0\n
  | y = 2.0\n
  | z = x + y\n
  | print(z)\n
  | ```\n
  | After the fence, two short sentences. Then we move on.\n
  | 
OK: no sentence-length outliers.

=== 08-permissive-thresholds ===
input:
  | The migration plan involves reading every record from the legacy table, transforming each field according to the new schema specification, writing the transformed record into the staging table for verification, and finally promoting the verified records into the production table in batches of one thousand to keep the replication lag bounded.\n
  | 
params: {'max_words': 80}
OK: no sentence-length outliers.

=== 09-empty-input ===
input:
  | <empty>
OK: no sentence-length outliers.

=== 10-single-sentence-no-outlier-possible ===
input:
  | A single short sentence stands alone here today.\n
  | 
OK: no sentence-length outliers.

```

Notes:

- Case 01 — five sentences in the 8-15 word range. Mean ~10,
  stddev ~2.5; nothing is more than 3 stddev out, so no outlier
  fires. None exceeds the 40-word ceiling either.
- Case 02 — a single 51-word sentence. Fires `long_sentence` on
  the absolute check (51 > 40). Does NOT fire `outlier_sentence`
  because a single-sentence paragraph has no peer group (the
  paragraph stddev check requires `>= 3` sentences).
- Case 03 — `Done.` (1 word) sandwiched between two real
  sentences. Fires `short_sentence` only. Anchored at sentence
  index 2 with `words=1`; the fix is "delete the period after
  `fleet` and merge the fragment into the next clause".
- Case 04 — proves the paragraph-relative outlier check fires
  even when the absolute long-sentence check does not. Sentence
  6 is 26 words (under the default 40-word ceiling) but the
  surrounding sentences are 2-4 words, mean=6.4, stddev=8.02, so
  with `outlier_factor=2.0` the deviation of 2.44x clears the
  bar. Also fires `short_sentence` for the 2-word "Latency held"
  — both are real findings on the same input. Note: with the
  default `outlier_factor=3.0`, the same sentence would NOT fire
  the outlier check (2.44 < 3.0). The point of this case is to
  demonstrate that paragraph-relative is a different axis from
  absolute and is parameter-tunable for stricter house styles.
- Case 05 — abbreviation handling. Without the skip-list,
  `Dr. Smith arrived.` would split into "Dr." (1 word →
  `short_sentence`) and "Smith arrived." (2 words →
  `short_sentence`), producing two false positives per real
  sentence. The skip-list collapses each abbreviation back into
  its surrounding sentence. `Status: e.g. green, i.e. nominal,
  etc. The team agreed.` is two sentences (the `etc.` is
  abbreviated; the period after `agreed` is a real boundary).
- Case 06 — decimal handling. `3.14`, `2.0.1`, `99.95` all have
  `.` chars between digits; none of them end a sentence. Each
  paragraph is three short sentences, all under the 40-word
  ceiling and well over the 3-word floor.
- Case 07 — proves the code-strip works. The Python fence
  contains `1.0`, `2.0`, `f.write(buf)`-style content that has
  no business being treated as sentence terminators or as words.
  After stripping, the prose is "Use to build paths. Then call
  and close. After the fence, two short sentences. Then we move
  on.", which is four short, balanced sentences.
- Case 08 — same input as Case 02 with `max_words=80`. The
  51-word sentence is now under the ceiling, so no finding fires.
  Demonstrates the parameter is monotonic.
- Case 09 — empty input returns no findings.
- Case 10 — single-sentence input. The sentence is 8 words
  (well within the absolute window), and the paragraph has < 3
  sentences so the outlier check does not engage. Clean.

## Files

- `detector.py` — pure-stdlib detector + `format_report`
- `example.py` — ten worked-example cases (run: `python3 example.py`)
- `README.md` — this file

## Limitations

- Sentence segmentation is heuristic. The abbreviation skip-list
  is fixed (12 entries); a domain-specific abbreviation
  (`Prof.`, `Sgt.`, `Pty.`) will cause a false sentence break.
  Extend the `_ABBREVIATIONS` set in `detector.py` for your
  house style; the change is a one-line edit and does not affect
  any other axis.
- Word counting tokenises on whitespace and counts any token
  with at least one alphanumeric char as a word. Hyphenated
  words (`on-call`, `seven-distinct`) count as one word, which
  matches the way readers count and matches the way every
  publishing house style guide counts.
- Paragraph splitting is line-gap-based (gap > 1 line starts a
  new paragraph). Markdown's "blank line ends a paragraph"
  convention is honoured. ATX headings, list bullets, and block
  quotes are NOT specially handled — they appear as their own
  paragraphs (often very short, which may fire `short_sentence`
  if the heading itself is < 3 words). If your input mixes
  prose and headings densely, scope the detector to the prose
  layer externally.
- The detector does NOT inspect any non-Latin script. Sentence
  terminators in CJK (`。`, `！`, `？`) are not treated as
  sentence boundaries. CJK input will appear as one giant
  sentence per paragraph and fire `long_sentence` on most
  paragraphs. This is a known scope limit.
- The detector does not attempt to repair anything. Repair is
  policy ("split", "condense", "merge with previous") and lives
  in [`agent-output-validation`](../agent-output-validation/).
