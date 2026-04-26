# `llm-output-empty-list-bullet-detector`

Pure-stdlib detector for **empty Markdown list bullets** — a
common LLM artifact where the model commits to a list shape
(`- `, `* `, `1.`) and then either runs out of token budget,
hallucinates that it already wrote the content, or emits only
invisible whitespace where content should be. Markdown
renderers happily render the empty `<li>` and most linters
ignore it, so the artifact lands in PR descriptions, runbooks,
and status updates unchallenged.

Three finding kinds:

- `empty_unordered_bullet` — `- `, `* `, or `+ ` followed only
  by ASCII whitespace (or nothing) until end of line.
- `empty_ordered_bullet`   — `<digits>.` or `<digits>)` followed
  only by ASCII whitespace.
- `whitespace_only_bullet` — bullet marker followed only by
  **invisible / non-ASCII whitespace** (NBSP `\u00a0`, ZWSP
  `\u200b`, em-space, ideographic space, etc.). Reported
  separately because it indicates the model tried to produce
  content and emitted invisible bytes — a different failure
  mode than "skipped the item entirely".

Fenced code blocks (` ``` ` or `~~~`) are skipped wholesale.
Indentation is preserved, so a nested empty bullet still
fires.

## When to use

- Pre-publish gate on any LLM-generated **PR description**,
  **runbook**, **release note**, or **status update** before
  it is written to a permanent record. An empty bullet reads
  as "the author abandoned this point", which is exactly the
  signal you do not want on a polished doc.
- Inside a **review-loop** validator: the per-finding
  `(line_number, marker)` tuple is small and stable, so a
  stuck repair loop is detectable across attempts (same
  tuple twice in a row → bail to a human).
- As a **template-rendering postcondition**: when a prompt
  template asks the model to fill a bullet list of N items, an
  empty bullet is a hard signal that N was wrong or the
  context window was exhausted mid-list.

## Usage

```
python3 detector.py [FILE ...]   # FILEs, or stdin if none
```

Exit code: `0` clean, `1` at least one finding. JSON on stdout.
Pure-stdlib; no third-party deps.

## Composition

- `agent-output-validation` — feed the JSON `findings` array
  into a repair prompt verbatim. Each finding's `raw_line` is
  enough context for the model to identify which bullet to
  refill.
- `llm-output-list-count-mismatch-detector` — orthogonal:
  that template enforces *how many* bullets exist, this
  enforces that each bullet *has content*. Together they
  catch both "wrong count" and "right count, half empty".
- `structured-output-repair-loop` — use `detect_empty_bullets`
  as the per-attempt validator. The `count` field collapses
  to a single integer per attempt for trivial loop-stuckness
  detection.

## Worked example

Input is `example_input.txt` (planted issues across all three
kinds, plus negative cases for fenced blocks, emphasis, and
decimal numbers).

```
$ python3 detector.py example_input.txt
```

Verbatim output (exit 1):

```json
{
  "count": 6,
  "findings": [
    {
      "kind": "empty_unordered_bullet",
      "line_number": 6,
      "marker": "-",
      "raw_line": "- "
    },
    {
      "kind": "whitespace_only_bullet",
      "line_number": 8,
      "marker": "-",
      "raw_line": "- \u00a0"
    },
    {
      "kind": "empty_unordered_bullet",
      "line_number": 9,
      "marker": "*",
      "raw_line": "* "
    },
    {
      "kind": "empty_ordered_bullet",
      "line_number": 15,
      "marker": "2.",
      "raw_line": "2."
    },
    {
      "kind": "empty_ordered_bullet",
      "line_number": 17,
      "marker": "4.",
      "raw_line": "4. "
    },
    {
      "kind": "empty_unordered_bullet",
      "line_number": 29,
      "marker": "-",
      "raw_line": "  - "
    }
  ],
  "ok": false
}
```

Notes:

- Line 8 (`- \u00a0`) is reported as `whitespace_only_bullet`,
  not `empty_unordered_bullet`. The distinction matters: an
  NBSP-only bullet is a model that *thinks* it produced
  content, and the right repair prompt is "you emitted
  invisible whitespace, replace it with real text" — quite
  different from "you skipped the item".
- Line 15 (`2.` with no trailing space at all) and line 17
  (`4. ` with trailing space) are both flagged as
  `empty_ordered_bullet`. The detector accepts both forms.
- Lines 22-25 are inside a fenced block and are **NOT**
  flagged, even though they look like empty bullets.
- Line 29 (`  - `) is a nested empty bullet and IS flagged —
  the detector preserves indentation rather than restricting
  to top-level lists.
- `*emphasised text*` and `1.5x speed` are correctly NOT
  flagged: the marker disambiguator requires a separator
  space or tab after the marker, so `*emphasis*` and the
  decimal `1.5` are not mistaken for bullets.

## Files

- `detector.py` — pure-stdlib detector + JSON renderer + CLI
- `example_input.txt` — planted-issue input, includes an NBSP
- `README.md` — this file

## Limitations

- Setext-style lists (which Markdown does not have) and
  task-list checkboxes (`- [ ]`) are out of scope. A
  `- [ ]` is NOT empty — it has content `[ ]`. If your
  house style treats unchecked task items as "empty" at
  some checkpoint, that belongs in a separate detector.
- A bullet that contains only the literal characters `TODO`
  or `tbd` is **NOT** flagged. Those are legitimate strings
  with semantics; flagging them belongs to a stylistic
  linter, not a structural one.
- The detector only inspects line shape, not list semantics.
  An ordered list that jumps `1. 3. 4.` is unaffected here;
  see `llm-output-markdown-ordered-list-numbering-monotonicity-validator`
  for that concern.
