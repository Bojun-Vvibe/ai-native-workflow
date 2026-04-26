# `llm-output-trailing-whitespace-and-tab-detector`

Pure stdlib detector for trailing whitespace, trailing tabs, stray
in-body tabs, and mixed-indent in an LLM Markdown output blob — the
class of artifact that survives `gh pr create`, `git commit -m`,
`gh issue create`, and any other "pipe a model-drafted blob into a
permanent record" workflow because the model output never passes
through your editor's trim-on-save hook.

Four finding kinds, fence-aware:

- `trailing_space` — line ends with one or more space chars before
  the newline. Reported once per line. Suppressed inside fenced code
  blocks (some languages — patches, diff, makefile recipes — treat
  trailing whitespace as semantic).
- `trailing_tab` — line ends with a tab (or tab + spaces). Reported
  separately from `trailing_space` because trailing tabs are even
  more invisible in rendered Markdown and trip a different class of
  editor settings; the fence on a `git log --color` line gets
  shifted instead of just padded. Same fence suppression rule.
- `stray_tab` — a tab appears in the BODY of a prose line (after
  the indent prefix). Markdown renderers turn this into either a
  giant gap or a hard-tab depending on viewer; almost always a
  model artifact (humans rarely emit a literal `\t` mid-sentence).
  Suppressed inside fenced code blocks.
- `mixed_indent` — a single line begins with both spaces AND tabs
  mixed in any order. Indent width is then ambiguous and renders
  inconsistently across viewers. Reported even inside fences (mixed
  indent is broken regardless of context).

A "fenced code block" is a region between two lines whose first
non-blank content is exactly ` ``` ` or `~~~` (optionally followed
by an info string). The matching close fence must use the same
character. The fence lines themselves are checked as prose — a
trailing tab on the close-fence line is a finding (case 06 in the
worked example proves it).

## When to use

- Pre-publish gate on any LLM-generated **commit message body**,
  **PR description**, or **issue body** before `gh` /  `git` writes
  it to a permanent record. The artifacts are invisible at compose
  time but show up forever in `git log` and `gh pr view`.
- Pre-flight for an LLM-drafted **runbook** /  **status report**
  pasted into a Slack-equivalent or wiki: trailing tabs in
  monospace channels render as 8-column gaps; this catches them
  before paste.
- Audit step in a **review-loop** that promotes
  [`agent-output-validation`](../agent-output-validation/)'s
  `repair_once` policy: a `stray_tab` finding feeds the offending
  line back into the repair prompt with a single instruction
  ("replace the tab at column N with a single space").
- Cron-friendly: findings are sorted by `(line_number, kind)` and
  the report is rendered in a deterministic format, so byte-
  identical output across runs makes diff-on-the-output a valid
  CI signal.

## Inputs / outputs

```
detect_whitespace_issues(text: str) -> list[Finding]

Finding(kind: str, line_number: int, column: int, raw: str, detail: str)
```

- `text` — the LLM output to scan. Must be `str` (raises
  `ValidationError` otherwise).
- `Finding.line_number` is 1-based; `Finding.column` is 1-based and
  points at the first offending char so a `sed` fix is mechanical.
- `Finding.raw` is the full line (without the trailing newline) so
  a reviewer reading the report does not have to jump back to the
  source. Tabs are rendered as `\t` in the report so the offending
  byte is visible.
- `format_report(findings)` renders a deterministic plain-text
  report. Empty list → `"OK: no trailing whitespace or stray tabs.\n"`.

Pure function: no I/O, no Markdown parser, no language detection.
The detector applies a single forward pass over the lines tracking
fence state.

## Composition

- [`agent-output-validation`](../agent-output-validation/) — feed a
  finding's `line_number`, `column`, and `kind` into the repair
  prompt for a one-turn fix; this template is the validator behind
  the `repair_once` policy for any prose output that will land in a
  permanent record.
- [`structured-output-repair-loop`](../structured-output-repair-loop/) —
  the per-attempt validator inside the loop's `validate(attempt)`
  callback; the `(line_number, column, kind)` tuple makes a stuck
  loop detectable (same tuple twice in a row → bail rather than
  burn another turn).
- [`llm-output-bullet-terminal-punctuation-consistency-validator`](../llm-output-bullet-terminal-punctuation-consistency-validator/) —
  orthogonal: that template enforces *what* terminates each bullet
  body, this enforces that nothing *invisible* trails any line. Run
  both on the same blob — both use the same `Finding` shape and the
  same stable sort, so a single CI step can union their findings.
- [`llm-output-quote-style-consistency-validator`](../llm-output-quote-style-consistency-validator/) —
  orthogonal: that template enforces quote-style consistency, this
  enforces line-ending and indent hygiene. Both use the deterministic
  per-`(line, kind)` sort so unioned reports stay diffable.
- [`structured-error-taxonomy`](../structured-error-taxonomy/) —
  classifies as `do_not_retry / attribution=model` for any of the
  four kinds. Trailing whitespace is a model artifact; retrying the
  same call against the same model is unlikely to change it without
  a corrective system message.

## Worked example

```
$ python3 example.py
```

Verbatim output:

```
=== 01-clean ===
input:
  | Daily summary:
  | - shipped two templates.
  | - ran the linter.
OK: no trailing whitespace or stray tabs.

=== 02-trailing-space ===
input:
  | Status:   
  | - ok
FOUND 1 whitespace finding(s):
  [trailing_space] line=1 col=8 :: 3 trailing whitespace char(s): '···'
    line='Status:   '

=== 03-trailing-tab ===
input:
  | Checklist:
  | - first item.
  | - second item.	  
  | - third item.
FOUND 2 whitespace finding(s):
  [stray_tab] line=3 col=15 :: tab character in prose body
    line='- second item.\\t  '
  [trailing_tab] line=3 col=15 :: 3 trailing whitespace char(s): '\\t··'
    line='- second item.\\t  '

=== 04-stray-tab-in-body ===
input:
  | Notes:
  | The deploy step	occasionally fails.
FOUND 1 whitespace finding(s):
  [stray_tab] line=2 col=16 :: tab character in prose body
    line='The deploy step\\toccasionally fails.'

=== 05-mixed-indent ===
input:
  | Outline:
  |  	- nested item with mixed indent
  |   - clean nested item
FOUND 1 whitespace finding(s):
  [mixed_indent] line=2 col=1 :: line begins with 2 indent chars mixing spaces and tabs
    line=' \\t- nested item with mixed indent'

=== 06-fenced-code-trailing-ws ===
input:
  | See snippet:
  | ```
  | x = 1   
  | y = 2
  | ```	
  | End.
FOUND 1 whitespace finding(s):
  [trailing_tab] line=5 col=4 :: 1 trailing whitespace char(s): '\\t'
    line='```\\t'

```

Notes:

- Case 02 — three trailing spaces after `Status:` are visually
  invisible and survive a copy-paste into `gh issue create`. The
  detector pinpoints column 8 (the byte right after the colon and
  the one expected space) so the fix is `sed -E 's/[[:space:]]+$//'`
  on exactly that line.
- Case 03 — the line trips both `stray_tab` AND `trailing_tab`
  because the tab character is in the body AND at the end. The two
  findings sort together by `line_number` so the reviewer sees both
  axes for the same line in adjacent lines of the report; the column
  on both is 15 (the tab byte itself).
- Case 04 — a tab character mid-sentence renders as a giant gap in
  most viewers. The detector finds it at column 16. Humans almost
  never emit literal mid-sentence tabs, so a `stray_tab` finding is
  a strong signal of model artifact.
- Case 05 — `" \t"` indent (one space then a tab) is a common model
  artifact when the model thinks "indent two columns" but emits the
  characters in the wrong order. Renders inconsistently between
  viewers (some show 9-column indent, some show 1+8). The detector
  reports it once at column 1 with the offending indent count.
- Case 06 — proves the fence-awareness invariant. Line 3 has three
  trailing spaces INSIDE the fence and is correctly NOT reported
  (some languages need them). Line 5 is the close fence itself and
  has a trailing tab — it IS reported, because the fence line is
  treated as prose, and a stray tab on a fence breaks Markdown
  rendering in some viewers (the close-fence is not recognized).

## Files

- `validator.py` — pure stdlib detector + `format_report`
- `example.py` — six worked-example cases (run: `python3 example.py`)
- `README.md` — this file

## Limitations

- Indented code blocks (the 4-space variant) are NOT special-cased.
  If you need different treatment, fence them with ` ``` `.
- The fence parser does not understand language info strings beyond
  "fence opens with this character"; a fence opened with ` ``` ` and
  closed with `~~~` is treated as never-closed. In practice, models
  do not mix fence chars within a single output.
- A line that consists entirely of whitespace (e.g. `"    \n"`) is
  reported as `trailing_space` — this is intentional. A blank line
  should be byte-equal to `"\n"`, not `"    \n"`, or downstream
  diffs flap.
