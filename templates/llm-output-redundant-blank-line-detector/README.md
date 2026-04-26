# `llm-output-redundant-blank-line-detector`

Pure-stdlib detector for redundant (3+) consecutive blank lines in an
LLM Markdown / prose output blob — the artifact class CommonMark and
every production renderer collapse to a single visual gap, so the
extra bytes are invisible at compose time but real on every metric
that touches the bytes themselves: tokens, diffs, paragraph
splitters.

Four finding kinds:

- `redundant_blank_run` — a run of `>= max_allowed_blanks + 1`
  consecutive blank lines anywhere in the body. One finding PER RUN,
  anchored at the 1-based line number of the first blank line in the
  run, with `detail` reporting the run length and the configured
  threshold so the operator can tell at a glance whether to relax
  the threshold or fix the input.
- `whitespace_only_blank` — a blank line that is not literally empty
  but contains only horizontal whitespace (`" "`, `\t`). Reported per
  occurrence, separately from `redundant_blank_run`, because the
  fix is different: `redundant_blank_run` is "delete N lines",
  `whitespace_only_blank` is "trim this one line". A `" \n"` line
  is the most invisible variant of all — not visible in source, not
  visible in render, still costs a token and still survives every
  trim-on-save hook the model never ran through.
- `leading_blank` — the blob begins with one or more blank lines.
  Reported once with the leading-blank count. A model that opens a
  response with a blank line is leaking a chat template artifact;
  every downstream renderer drops it visually but the byte is in
  the audit log forever.
- `trailing_blank_run` — the blob ends with `>= 2` blank lines
  before EOF. Reported once with the trailing-blank count. POSIX
  text convention is exactly one trailing newline (which renders as
  zero blank lines after the last content line), so a single
  trailing blank line is *not* flagged — only 2-or-more is.

A "blank line" is one whose content is empty OR consists exclusively
of horizontal whitespace. The detector treats both as blank because
every render engine does, and treating them differently would let
the most invisible bug class slip through.

## When to use

- Pre-publish gate on any LLM-generated **commit message body**,
  **PR description**, or **issue body** before `gh` / `git` writes
  it to a permanent record. A 4-blank-line run renders identical to
  a single blank line in the GitHub UI but bloats `git log` and the
  next regeneration's diff (4 → 5 → 7 → 3 across regenerations is
  pure noise churn).
- Pre-flight on an LLM-drafted **runbook** / **status update**
  before paste into a wiki: a 3+ blank run before paste becomes a
  single blank in the wiki's renderer, but back-export from the
  wiki re-emits a single blank — so the round-trip is destructive
  and you cannot diff "what was published" against "what was
  drafted" cleanly.
- Audit step in a **review-loop** that promotes
  [`agent-output-validation`](../agent-output-validation/)'s
  `repair_once` policy: a blob-scope `leading_blank` or
  `trailing_blank_run` finding is one-shot fixable with a single
  trim instruction; multiple `redundant_blank_run` findings can
  feed a "collapse all blank-line runs to a single blank line"
  one-turn fix.
- Cron-friendly: findings are sorted by `(line_number, kind)` and
  the report is deterministic, so byte-identical output across
  runs makes diff-on-the-output a valid CI signal.

## Inputs / outputs

```
detect_redundant_blank_lines(text: str, *, max_allowed_blanks: int = 1) -> list[Finding]

Finding(kind: str, line_number: int, detail: str)
```

- `text` — the LLM output to scan. Must be `str` (raises
  `ValidationError` otherwise). The detector operates on the
  in-memory `str` BEFORE any sink encodes it, so it sees the bytes
  the model actually emitted.
- `max_allowed_blanks` — threshold for a run to be considered
  redundant. Default `1` (so any run of 2 or more blank lines
  fires). Set to `2` for CommonMark-permissive (only 3+ fires —
  the literal-titular threshold the template name promises). Set
  to `0` for strict "no blank lines at all" (compact log output,
  slack-paste-ready prose). Negative values raise `ValidationError`.
- `Finding.line_number` is 1-based and points at the FIRST blank
  line in a run (for `redundant_blank_run` / `leading_blank` /
  `trailing_blank_run`) or at the offending whitespace-only line
  itself (for `whitespace_only_blank`).
- `format_report(findings)` renders a deterministic plain-text
  report. Empty list → `"OK: no redundant blank lines.\n"`.

Pure function: no I/O, no Markdown parser, no language detection,
no normalisation. The detector is read-only.

## Composition

- [`agent-output-validation`](../agent-output-validation/) — feed a
  `redundant_blank_run` finding's `detail` directly into the
  repair prompt; the run-length number gives the model exactly the
  signal it needs ("collapse 3 consecutive blanks down to 1").
- [`structured-output-repair-loop`](../structured-output-repair-loop/) —
  the per-attempt validator inside the loop's `validate(attempt)`
  callback. The `(line_number, kind, run_length)` triple is a
  stable fingerprint, so a stuck loop is detectable (same triple
  two attempts in a row → bail rather than burn another turn on
  whitespace).
- [`llm-output-trailing-whitespace-and-tab-detector`](../llm-output-trailing-whitespace-and-tab-detector/) —
  orthogonal: that template enforces what's BEFORE each line
  ending (trailing spaces / tabs after content), this enforces
  what's BETWEEN content lines (excess blank lines). Both use the
  same `Finding` shape and the same stable sort, so a single CI
  step can union their findings.
- [`llm-output-mixed-line-ending-detector`](../llm-output-mixed-line-ending-detector/) —
  orthogonal axis: mixed-line-ending detector enforces what the
  line ending IS, this template enforces how many of them stack
  back-to-back. Run mixed-line-ending first (normalize CRLF → LF)
  then this one (so the blank-line counting is post-normalization).
- [`structured-error-taxonomy`](../structured-error-taxonomy/) —
  classifies as `do_not_retry / attribution=model` for any of the
  four kinds. Re-running the same call on the same model is
  unlikely to change blank-line behaviour without a corrective
  system message.

## Worked example

```
$ python3 example.py
```

Verbatim output:

```
=== 01-clean-single-blanks ===
input:
  | First paragraph.\n
  | \n
  | Second paragraph.\n
  | \n
  | Third paragraph.\n
  | 
OK: no redundant blank lines.

=== 02-double-blank-flagged-by-default ===
input:
  | First paragraph.\n
  | \n
  | \n
  | Second paragraph.\n
  | 
FOUND 1 blank-line finding(s):
  [redundant_blank_run] line=2 :: run of 2 consecutive blank line(s) (allowed: 1)

=== 03-double-blank-permissive ===
input:
  | First paragraph.\n
  | \n
  | \n
  | Second paragraph.\n
  | \n
  | \n
  | \n
  | Third paragraph.\n
  | 
params: {'max_allowed_blanks': 2}
FOUND 1 blank-line finding(s):
  [redundant_blank_run] line=5 :: run of 3 consecutive blank line(s) (allowed: 2)

=== 04-leading-and-trailing-blanks ===
input:
  | \n
  | \n
  | Intro line.\n
  | \n
  | \n
  | Body line.\n
  | \n
  | \n
  | \n
  | 
FOUND 3 blank-line finding(s):
  [leading_blank] line=1 :: blob opens with 2 blank line(s)
  [redundant_blank_run] line=4 :: run of 2 consecutive blank line(s) (allowed: 1)
  [trailing_blank_run] line=7 :: blob ends with 3 blank line(s) before EOF

=== 05-whitespace-only-blank-line ===
input:
  | Heading\n
  | \n
  |    \t\n
  | \n
  | Body.\n
  | 
FOUND 2 blank-line finding(s):
  [redundant_blank_run] line=2 :: run of 3 consecutive blank line(s) (allowed: 1)
  [whitespace_only_blank] line=3 :: blank line is whitespace-only (spaces=3, tabs=1)

=== 06-strict-no-blank-lines ===
input:
  | log line one\n
  | \n
  | log line two\n
  | log line three\n
  | 
params: {'max_allowed_blanks': 0}
FOUND 1 blank-line finding(s):
  [redundant_blank_run] line=2 :: run of 1 consecutive blank line(s) (allowed: 0)

=== 07-only-newlines ===
input:
  | \n
  | \n
  | \n
  | \n
  | 
FOUND 2 blank-line finding(s):
  [leading_blank] line=1 :: blob opens with 4 blank line(s)
  [trailing_blank_run] line=1 :: blob ends with 4 blank line(s) before EOF

```

Notes:

- Case 01 — single blank lines between paragraphs are canonical
  Markdown and pass clean. The default threshold deliberately does
  NOT flag the single-blank-line case because that's exactly the
  Markdown paragraph separator.
- Case 02 — proves the default threshold (`max_allowed_blanks=1`)
  fires on the first run of 2 blanks. The literal `\n\n\n` in
  source is two blank lines (the lines BETWEEN the three newlines)
  collapsed by every renderer to one visual gap.
- Case 03 — proves the permissive threshold. Same input shape as
  Case 02 plus a 3-blank run; with `max_allowed_blanks=2` the
  2-blank run is silently allowed and only the 3-blank run fires.
  This matches the literal "3+ consecutive" reading of the
  template name; the default is one stricter because in practice
  even 2 consecutive blanks are pure noise.
- Case 04 — proves all three blob-scope finding kinds fire
  independently and that the interior `redundant_blank_run` is NOT
  double-counted with the leading or trailing runs. The leading
  2-blank run and the trailing 3-blank run are reported by their
  dedicated kinds; only the interior 2-blank run between content
  lines fires `redundant_blank_run`.
- Case 05 — the whitespace-only line at line 3 (`"   \t"`) IS a
  blank for run-counting purposes (so the 3-line run is reported)
  AND is also separately flagged with its own `whitespace_only_blank`
  finding so the operator sees both axes for the same line. The
  fix order is "trim line 3 first, then the run shrinks to 2 (or
  0 depending on what trimmed to); rerun the detector".
- Case 06 — proves the strict policy. With `max_allowed_blanks=0`
  even a SINGLE blank line fires (`run of 1 consecutive blank
  line(s) (allowed: 0)`). Use this for a compact-log mode where
  every blank line is wasted bytes.
- Case 07 — pathological. A blob that's nothing but newlines
  reports BOTH `leading_blank` and `trailing_blank_run` because
  both are true (the blank run starts at line 1 AND ends at the
  last line). No `redundant_blank_run` fires because the interior
  is empty (leading and trailing claimed all the lines).

## Files

- `detector.py` — pure-stdlib detector + `format_report`
- `example.py` — seven worked-example cases (run: `python3 example.py`)
- `README.md` — this file

## Limitations

- The detector does NOT inspect the bytes inside fenced code
  blocks specially: a 5-blank-line run inside a ` ``` ` fence is
  reported the same as a run in prose. This is intentional — most
  languages (Python, shell, YAML) treat 5 consecutive blank lines
  as semantically meaningless too, and a model that emits them
  inside a code block is leaking the same artifact. If your house
  style legitimately ships ASCII art that requires preserved
  blank-line patterns inside fences, scope the detector to the
  prose part externally.
- A blob that is exactly the empty string `""` returns `[]` (no
  findings). An empty blob has no blank lines to be redundant.
- The detector does not attempt to repair anything. Repair is
  trivially a `re.sub(r'\n{3,}', '\n\n', text)` (collapse all
  blank-line runs to a single blank line), or lives in
  [`agent-output-validation`](../agent-output-validation/)
  depending on policy.
- The line-number anchor for the trailing-blank summary in Case 07
  is the FIRST blank in the run from the top of the file, which
  for an all-blank file collides with the leading-blank anchor.
  This is correct: the same lines are simultaneously the leading
  AND trailing run when the file is nothing but blanks. Two
  findings, one anchor — the kind disambiguates.
