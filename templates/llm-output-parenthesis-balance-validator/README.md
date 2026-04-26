# `llm-output-parenthesis-balance-validator`

Pure-stdlib validator for round-paren `(` / `)` balance and nesting
depth in an LLM prose / Markdown output blob — a failure mode that
streaming LLMs hit constantly when a sentence opens a parenthetical
aside, drifts into a clarification, and forgets to close before the
next sentence boundary.

Square brackets `[ ]` and curly braces `{ }` are deliberately OUT of
scope here — they have legitimate Markdown semantics (link reference
syntax, footnote syntax, template placeholders) and are covered by
sibling templates
([`llm-output-citation-bracket-balance-validator`](../llm-output-citation-bracket-balance-validator/),
[`llm-output-quotation-mark-balance-validator`](../llm-output-quotation-mark-balance-validator/)).
This validator owns ONE axis: the round paren that nobody else
checks.

Four finding kinds:

- `unmatched_open` — a `(` with no matching `)` before EOF. One
  finding PER unmatched open, anchored at its 1-based line and
  1-based column. The single most common LLM output bug in this
  family — a long sentence with a parenthetical that runs past
  its own close.
- `unmatched_close` — a `)` with no preceding unmatched `(`. One
  finding per occurrence, anchored at line/column of the `)`. Less
  common than `unmatched_open` in practice but it does show up
  when a model tries to "balance" a hallucinated open from earlier
  in the response.
- `excessive_nesting` — at any point the live open-paren depth
  exceeds `max_depth` (default 3). Reported once per RUN that
  crossed the threshold (not once per char that stayed above it),
  anchored at the `(` that pushed depth above the threshold. A
  prose paragraph that nests three deep is already at the
  readability ceiling; four-deep is a code paste pretending to be
  prose.
- `inside_code_paren_skipped` (informational summary) — number of
  paren chars that were ignored because they sit inside a fenced
  code block (` ``` `) or an inline code span (`` ` ``). Reported
  once at line 1, column 1 with the skipped count, so the operator
  can tell whether a "balanced" report is balanced in the prose
  layer or just because most of the parens were in code. Suppress
  with `report_skipped=False`.

Code-aware scope: the validator tracks fenced code blocks (lines
whose first non-space chars are `` ``` ``, toggling the fence on
each occurrence) and inline backtick spans. Parens inside either
are NOT counted toward balance — `print("hello (world)")` inside a
Python fence has no business raising `unmatched_close`.

## When to use

- Pre-publish gate on any LLM-drafted **PR description**, **commit
  body**, or **incident note** before `gh` / `git` writes it.
  GitHub renders an unbalanced paren without complaint, but a
  reader scanning for the close in a 200-word paragraph wastes
  attention budget. Catch it before paste.
- Pre-flight on an LLM-generated **release note** or **changelog
  entry**. A `(see #1234` with no close usually means the model
  cut off mid-thought; the missing context is exactly what the
  reader was promised.
- Inline guard inside a
  [`structured-output-repair-loop`](../structured-output-repair-loop/) —
  the validator is a pure function with a stable
  `(line_number, column, kind)` fingerprint, so a rerun that
  produces the same finding twice in a row is a "do not retry,
  the model is stuck" signal.
- Audit step paired with
  [`llm-output-quotation-mark-balance-validator`](../llm-output-quotation-mark-balance-validator/) —
  unmatched parens and unmatched quotes share the same
  truncated-stream root cause; checking both at once catches the
  whole class.

## Inputs / outputs

```
validate_parenthesis_balance(
    text: str,
    *,
    max_depth: int = 3,
    report_skipped: bool = True,
) -> list[Finding]

Finding(kind: str, line_number: int, column: int, detail: str)
```

- `text` — the LLM output to scan. Must be `str` (raises
  `ValidationError` otherwise). The validator operates on the
  in-memory `str` BEFORE any sink encodes it.
- `max_depth` — maximum tolerated live open-paren depth before
  `excessive_nesting` fires. Default 3. Set to 1 for strict
  business-writing style (no nested parens at all). Values < 1
  raise `ValidationError`.
- `report_skipped` — if True (default), emit a single
  `inside_code_paren_skipped` summary finding when any paren char
  was ignored inside code. Set False for a strictly finding-only
  report.
- `Finding.line_number` / `Finding.column` are both 1-based and
  point at the offending character (the `(` for `unmatched_open`
  and `excessive_nesting`, the `)` for `unmatched_close`).
- `format_report(findings)` renders a deterministic plain-text
  report. Empty list → `"OK: parentheses balanced.\n"`.

Pure function: no I/O, no Markdown parser, no language detection.
The fence / inline-code detection is intentionally minimal — see
`Limitations`.

## Composition

- [`llm-output-quotation-mark-balance-validator`](../llm-output-quotation-mark-balance-validator/) —
  same shape of bug on a different axis. Run both; union findings.
- [`llm-output-citation-bracket-balance-validator`](../llm-output-citation-bracket-balance-validator/) —
  owns `[ ]`, this template owns `( )`. Orthogonal.
- [`structured-output-repair-loop`](../structured-output-repair-loop/) —
  use the `Finding.detail` string as the repair prompt
  ("close the open paren at line 3 col 21"); the line/col anchor
  gives the model a precise edit target.
- [`structured-error-taxonomy`](../structured-error-taxonomy/) —
  classifies as `do_not_retry / attribution=model` for
  `unmatched_open` repeating across attempts (model keeps
  truncating the same parenthetical).

## Worked example

```
$ python3 example.py
```

Verbatim output:

```
=== 01-clean-balanced ===
input:
  | The model (correctly) closed every parenthesis (even the nested one (here)).\n
  | 
OK: parentheses balanced.

=== 02-unmatched-open ===
input:
  | We saw three issues (timeout, retry storm, stale cache.\n
  | 
FOUND 1 paren finding(s):
  [unmatched_open] line=1 col=21 :: '(' has no matching ')' before EOF

=== 03-unmatched-close ===
input:
  | The build failed) and nobody noticed for an hour.\n
  | 
FOUND 1 paren finding(s):
  [unmatched_close] line=1 col=17 :: ')' has no matching preceding '('

=== 04-excessive-nesting ===
input:
  | Logs (level=info (subsystem=auth (tenant=acme (region=us-east))) ) here.\n
  | 
FOUND 1 paren finding(s):
  [excessive_nesting] line=1 col=47 :: open-paren depth reached 4 (max allowed: 3)

=== 05-permissive-nesting ===
input:
  | Logs (level=info (subsystem=auth (tenant=acme (region=us-east))) ) here.\n
  | 
params: {'max_depth': 4}
OK: parentheses balanced.

=== 06-parens-inside-fenced-code-skipped ===
input:
  | Prose with one (paren) outside.\n
  | ```python\n
  | print("hello (world)")\n
  | if (x): pass\n
  | ```\n
  | More prose, also balanced (here).\n
  | 
FOUND 1 paren finding(s):
  [inside_code_paren_skipped] line=1 col=1 :: 6 paren char(s) ignored inside code (fenced block or inline span)

=== 07-parens-inside-inline-code-skipped ===
input:
  | Use `print(x)` to log, but the prose paren (this one) is real.\n
  | And here is `another(unmatched` span that the validator ignores.\n
  | 
FOUND 1 paren finding(s):
  [inside_code_paren_skipped] line=1 col=1 :: 3 paren char(s) ignored inside code (fenced block or inline span)

=== 08-strict-no-nesting ===
input:
  | Outer (with inner (nested) text) here.\n
  | 
params: {'max_depth': 1}
FOUND 1 paren finding(s):
  [excessive_nesting] line=1 col=19 :: open-paren depth reached 2 (max allowed: 1)

=== 09-multiple-unmatched-on-one-line ===
input:
  | Bad ((line)) is fine, but ( and ( and )))) here.\n
  | 
FOUND 2 paren finding(s):
  [unmatched_close] line=1 col=41 :: ')' has no matching preceding '('
  [unmatched_close] line=1 col=42 :: ')' has no matching preceding '('

=== 10-empty-input ===
input:
  | <empty>
OK: parentheses balanced.

```

Notes:

- Case 01 — three opens, three closes, all properly nested. The
  innermost `(here)` is at depth 3, exactly at the default ceiling
  but not over, so no `excessive_nesting` fires.
- Case 02 — the canonical streaming-LLM bug. The model opens at
  col 21 (`(timeout,`) and the sentence ends at the period without
  ever closing. Anchor points at the OPEN, not at EOF, because the
  open is the byte the operator needs to fix.
- Case 03 — orthogonal failure: a stray `)` with no preceding
  open. Anchored at the offending `)` (col 17 = the `)` after
  "failed"). Reported as a separate kind so a one-shot fix prompt
  can target the right edit ("delete the `)` at line 1 col 17").
- Case 04 — proves `excessive_nesting` fires ONCE per run that
  crosses the threshold, not once per char that stays above it.
  Depth climbs 1 → 2 → 3 → 4 at col 47 (the `(region=us-east)`
  open), the finding fires there, and even though depth stays at
  4 for several more chars it is NOT re-reported.
- Case 05 — same input as Case 04 with `max_depth=4`. The depth
  ceiling is now exactly the peak, so no finding fires. Proves
  the parameter is monotonic and the validator is stable.
- Case 06 — three open / three close in the prose layer, all
  balanced. Inside the Python fence there are 3 `(` and 3 `)`
  (6 chars total) which would have unbalanced (the inner `(world)`
  is balanced but `print(...)` and `if (x):` add 2 more pairs);
  all of them are skipped and the only finding is the
  informational summary `inside_code_paren_skipped`. Without the
  fence-aware logic this would falsely report nothing wrong AND
  silently let a real prose-paren bug slip through on a different
  document.
- Case 07 — same idea on a single line: the `print(x)` and
  `another(unmatched` inline-code spans contribute 3 paren chars
  (`(`, `)`, `(`) that are skipped; the prose `(this one)` is
  balanced. Note that the unbalanced `another(unmatched` span
  inside the inline code does NOT raise `unmatched_open` — that
  is the whole point of the code-aware scope.
- Case 08 — proves the strict policy. With `max_depth=1` even a
  single nested paren fires (depth reaches 2 at col 19 = the
  inner `(nested)` open). Use this for executive-summary prose
  where parentheticals must be flat.
- Case 09 — multiple unmatched closes on a single line. The
  prefix `((line))` balances (depth 0 again), then the bare `(`
  at col 27 and `(` at col 34 push depth to 2, then four `)` at
  cols 39, 40, 41, 42 close them all and over-close by 2. The
  first two `)` (cols 39, 40) match the two opens; cols 41, 42
  are the over-closes. Both are reported individually so a
  one-shot fix prompt can delete exactly two characters.
- Case 10 — empty input returns no findings. An empty blob has
  no parens to be unbalanced.

## Files

- `validator.py` — pure-stdlib validator + `format_report`
- `example.py` — ten worked-example cases (run: `python3 example.py`)
- `README.md` — this file

## Limitations

- Fence detection covers backtick fences (` ``` `) only; tilde
  fences (` ~~~ `) are not recognised. Most LLM output uses
  backticks; if your house style emits tilde fences, the parens
  inside them will be counted toward balance (which may produce
  false positives).
- Inline-code detection is single-backtick only. Double-backtick
  spans (`` `` `` for spans containing literal backticks) are not
  specially handled — the second backtick simply re-toggles the
  inline state, which is usually correct in practice but can be
  wrong in pathological inputs that mix span widths.
- The validator is paren-only: it does NOT check `[ ]`, `{ }`, or
  `< >`. Use the sibling templates listed in Composition for
  those axes.
- Escaped parens (`\(`, `\)`) are NOT recognised as escaped — they
  are counted as real parens. This is correct for prose (where
  the backslash is rendered literally) and wrong for some code
  embeddings; if you need escape-aware behaviour, scope this
  validator to the prose layer externally.
- The validator does not attempt to repair anything. Repair lives
  in [`agent-output-validation`](../agent-output-validation/) and
  is policy: append the missing `)`, delete the extra `)`, or
  flatten the over-nested expression.
