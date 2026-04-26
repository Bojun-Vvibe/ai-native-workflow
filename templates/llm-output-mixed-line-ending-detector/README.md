# `llm-output-mixed-line-ending-detector`

Pure-stdlib detector for mixed and stray line endings in an LLM
Markdown / prose output blob — the class of artifact that survives
`gh pr create`, `git commit -F -`, `gh issue create`, and any other
"pipe a model-drafted blob into a permanent record" workflow because
neither the editor nor the network ever normalises the bytes.

Five finding kinds:

- `mixed_endings` — the blob contains MORE THAN ONE distinct
  line-ending kind. Reported once, scope=blob, with the per-kind
  inventory (`lf=N crlf=N cr_only=N`).
- `cr_only` — a bare `\r` (classic-Mac terminator). In 2024+ output
  this is almost always a model artifact. Reported once per
  occurrence with the 1-based line number.
- `crlf_in_lf_blob` — a CRLF terminator embedded in an otherwise
  LF-majority blob. Reported per occurrence.
- `lf_in_crlf_blob` — a bare LF embedded in an otherwise CRLF-majority
  blob. Reported per occurrence.
- `trailing_no_eol` — the final byte of the blob is not a line
  ending. Only reported if the blob is non-empty.

Majority is decided by raw count; on a tie, the order is `lf > crlf
> cr`. The `mixed_endings` summary is emitted ONCE before any
per-line embedding finding, so a reviewer sees the inventory before
the per-line noise.

## When to use

- Pre-publish gate on any LLM-generated **commit message body**,
  **PR description**, or **issue body** before `gh` / `git` writes
  it to a permanent record. A stray CRLF in the middle of an LF
  blob renders as `^M` in `git log` forever.
- Pre-flight for an LLM-drafted **runbook** / **status update**
  before paste into a wiki or chat: bare CR characters truncate
  many Markdown renderers at the first occurrence (the rest of the
  line silently disappears).
- Audit step in a **review-loop** that promotes
  [`agent-output-validation`](../agent-output-validation/)'s
  `repair_once` policy: a `mixed_endings` finding gives the repair
  prompt a single concrete instruction ("re-emit the blob with LF
  line endings only; do not change any other byte").
- Cron-friendly: findings are sorted by `(line_number, kind)` and
  the summary line is deterministic, so byte-identical output
  across runs makes diff-on-the-output a valid CI signal.

## Inputs / outputs

```
detect_line_ending_issues(text: str) -> list[Finding]

Finding(kind: str, line_number: int, detail: str)
```

- `text` — the LLM output to scan. Must be `str` (raises
  `ValidationError` otherwise). The detector operates on the
  in-memory `str` BEFORE it is encoded for any sink, so it sees
  the bytes the model actually emitted.
- `Finding.line_number` is 1-based and points at the line whose
  TERMINATOR is the offender. The `mixed_endings` summary uses
  `line_number=0` (rendered `scope=blob`) to mark it as
  blob-scope rather than per-line.
- `format_report(findings)` renders a deterministic plain-text
  report. Empty list → `"OK: line endings are consistent.\n"`.

Pure function: no I/O, no Markdown parser, no language detection,
no normalisation. The detector is read-only.

## Composition

- [`agent-output-validation`](../agent-output-validation/) — feed a
  `mixed_endings` summary into the repair prompt verbatim; the
  inventory string is small and gives the model exactly the signal
  it needs ("re-emit with LF only").
- [`structured-output-repair-loop`](../structured-output-repair-loop/) —
  the per-attempt validator inside the loop's `validate(attempt)`
  callback. The blob-scope `mixed_endings` finding's detail string
  is stable across attempts, so a stuck loop is detectable (same
  inventory two attempts in a row → bail).
- [`llm-output-trailing-whitespace-and-tab-detector`](../llm-output-trailing-whitespace-and-tab-detector/) —
  orthogonal: that template enforces what's BEFORE each line ending,
  this enforces what the line ending IS. Both use the same
  `Finding` shape and the same stable sort, so a single CI step
  can union their findings.
- [`structured-error-taxonomy`](../structured-error-taxonomy/) —
  classifies as `do_not_retry / attribution=model` for any of the
  five kinds. Re-running the same call on the same model is unlikely
  to change line-ending behaviour without a corrective system
  message.

## Worked example

```
$ python3 example.py
```

Verbatim output:

```
=== 01-clean-lf ===
input:
  | Status: ok\n
  | - one\n
  | - two\n
  | 
OK: line endings are consistent.

=== 02-clean-crlf ===
input:
  | Status: ok\r\n
  | - one\r\n
  | - two\r\n
  | 
OK: line endings are consistent.

=== 03-mixed-lf-and-crlf ===
input:
  | intro line\n
  |  second line\r\n
  | third line\n
  | fourth line\r\n
  | 
FOUND 3 line-ending finding(s):
  [mixed_endings] scope=blob :: blob contains 2 distinct line-ending kinds: lf=2 crlf=2 cr_only=0
  [crlf_in_lf_blob] line=2 :: CRLF terminator inside an LF-majority blob
  [crlf_in_lf_blob] line=4 :: CRLF terminator inside an LF-majority blob

=== 04-bare-cr-classic-mac ===
input:
  | alpha\rbeta\rgamma\r
FOUND 3 line-ending finding(s):
  [cr_only] line=1 :: bare CR (classic-Mac) terminator
  [cr_only] line=2 :: bare CR (classic-Mac) terminator
  [cr_only] line=3 :: bare CR (classic-Mac) terminator

=== 05-cr-leak-into-lf-blob ===
input:
  | first\n
  | second\rthird\n
  | fourth\n
  | 
FOUND 2 line-ending finding(s):
  [mixed_endings] scope=blob :: blob contains 2 distinct line-ending kinds: lf=3 crlf=0 cr_only=1
  [cr_only] line=2 :: bare CR (classic-Mac) terminator

=== 06-trailing-no-eol ===
input:
  | headline\n
  | body paragraph without final newline
FOUND 1 line-ending finding(s):
  [trailing_no_eol] line=2 :: final line is not terminated by a line ending

```

Notes:

- Case 02 — a fully CRLF blob is CONSISTENT and is reported `OK`.
  This template flags MIXING and stray bare CR; it does not
  prescribe a house style. The decision "we want LF only" lives in
  a normalisation step, not here.
- Case 03 — the LF count and CRLF count are tied (2 and 2). The
  tie-break favours LF (the canonical Markdown / git form), so the
  CRLF lines are reported as `crlf_in_lf_blob`. If your house
  style is CRLF, swap the tie-break.
- Case 04 — a bare-CR-only blob is rare in the wild but is the
  classic "old model trained on Mac OS 9 era text" artifact.
  Reported as `cr_only` per line; no `mixed_endings` summary is
  emitted because there is only one kind present.
- Case 05 — proves that `mixed_endings` AND the per-line embedding
  finding are emitted in deterministic order: the blob-scope
  summary first (`line_number=0`), then the per-line finding at
  line 2. The summary's inventory makes the repair prompt
  one-shot fixable.
- Case 06 — `trailing_no_eol` is reported even on an
  otherwise-clean blob. POSIX text-file convention requires a
  trailing newline, and `git diff` renders the lack of one as
  `\ No newline at end of file` — invisible at compose time,
  permanent in `git log`.

## Files

- `validator.py` — pure-stdlib detector + `format_report`
- `example.py` — six worked-example cases (run: `python3 example.py`)
- `README.md` — this file

## Limitations

- The detector does NOT inspect the bytes inside fenced code
  blocks specially: a CRLF inside a ` ``` ` fence is reported the
  same as a CRLF in prose. This is intentional — a model that
  emits Windows line endings inside code blocks is leaking the
  same artifact, and most language toolchains hate CRLF in source
  too (Python, shell heredocs, Makefile recipes).
- A blob that is exactly the empty string `""` returns `[]` (no
  findings). An empty blob has no line endings to be inconsistent
  about.
- The detector does not attempt to repair anything. Repair lives
  in [`agent-output-validation`](../agent-output-validation/) or in
  a one-line `text.replace("\\r\\n", "\\n").replace("\\r", "\\n")`
  in the caller, depending on the policy.
