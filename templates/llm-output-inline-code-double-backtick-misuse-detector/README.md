# `llm-output-inline-code-double-backtick-misuse-detector`

Pure-stdlib detector for **inline-code spans delimited by
double backticks** ( ``...`` ) whose content **does not contain
a literal backtick**:

```
Use the ``foo`` function.
The ``--verbose`` flag enables it.
```

CommonMark only requires double backticks when the span itself
contains a literal backtick (so the parser can find the end).
When the content has no backtick, ``foo`` and `foo` render
identically, but the double form is:

- harder to read in source,
- easier to break under repair edits (one stray backtick
  flips the parse),
- a strong signal that the LLM cargo-culted a delimiter
  pattern from training data without thinking about it.

One finding kind:

- `unnecessary_double_backtick` — double-backtick inline span
  whose content has no literal backtick

The detector is deliberately conservative:

- Only flags **exactly two** opening / closing backticks. Triple
  or longer runs are out of scope.
- Fenced code blocks (` ``` ` and `~~~`) are skipped wholesale,
  so example Markdown in a tutorial does not self-trigger.
- Empty or whitespace-only spans ( ```` `` `` ```` with nothing
  between) are NOT flagged — those have separate semantics
  under CommonMark (one space trimmed each side).
- Spans whose content contains a literal backtick are NOT
  flagged — the double form is required there.
- Spans that span more than one line are NOT flagged (rare,
  fragile, separate concern).

The detector also emits a `suggested_fix` field with the
single-backtick form (and trims surrounding whitespace if the
double form was padded for backtick-content disambiguation that
turned out to be unnecessary).

## When to use

- Pre-publish gate on any LLM-generated **doc-site page**,
  **README**, **runbook**, **release note**, or **API
  reference** before merge. Once consistency is enforced
  one way, drift back to the double form is the most common
  regression.
- Inside a **review-loop validator**: each finding's
  `(line_number, column, suggested_fix)` triple is small and
  deterministic, so the same finding twice across repair
  attempts is a clean "give up and escalate" signal.
- As a **prompt-template postcondition**: when a template asks
  the model to "wrap identifiers in backticks", models often
  default to double for safety. This detector catches that
  drift mechanically.

## Usage

```
python3 detector.py [FILE ...]   # FILEs, or stdin if none
```

Exit code: `0` clean, `1` at least one finding. JSON to stdout.
Pure stdlib; no third-party deps.

## Composition

- `agent-output-validation` — feed the JSON `findings` array
  into a repair prompt verbatim. The `suggested_fix` field
  gives the model a one-shot replacement target.
- `llm-output-inline-code-backtick-balance-detector` —
  orthogonal: that template targets *unbalanced* spans, this
  one targets *over-delimited* but balanced spans. Run
  balance-check first; once balanced, run this one to tighten
  delimiters.
- `llm-output-fenced-code-language-tag-missing-detector` — run
  before this in a doc-quality pipeline; fenced blocks have
  to be well-formed before per-line inline-code analysis is
  meaningful.

## Worked example

Input is `worked-example/input.md` — planted issues plus
negative cases for required-double form, empty spans,
triple-backticks, fenced-block-internal spans, and multi-line
spans.

Actual end-to-end run, captured verbatim into
`worked-example/expected-output.txt`:

```
$ python3 detector.py worked-example/input.md
{
  "count": 7,
  "findings": [
    {
      "column": 9,
      "content": "foo",
      "content_length": 3,
      "kind": "unnecessary_double_backtick",
      "line_number": 3,
      "suggested_fix": "`foo`"
    },
    {
      "column": 5,
      "content": "--verbose",
      "content_length": 9,
      "kind": "unnecessary_double_backtick",
      "line_number": 5,
      "suggested_fix": "`--verbose`"
    },
    {
      "column": 10,
      "content": "has multiple words",
      "content_length": 18,
      "kind": "unnecessary_double_backtick",
      "line_number": 9,
      "suggested_fix": "`has multiple words`"
    },
    {
      "column": 16,
      "content": "alpha",
      "content_length": 5,
      "kind": "unnecessary_double_backtick",
      "line_number": 17,
      "suggested_fix": "`alpha`"
    },
    {
      "column": 43,
      "content": "gamma",
      "content_length": 5,
      "kind": "unnecessary_double_backtick",
      "line_number": 17,
      "suggested_fix": "`gamma`"
    },
    {
      "column": 50,
      "content": "  spaced  ",
      "content_length": 10,
      "kind": "unnecessary_double_backtick",
      "line_number": 19,
      "suggested_fix": "`spaced`"
    },
    {
      "column": 14,
      "content": "after-fence-flagged",
      "content_length": 19,
      "kind": "unnecessary_double_backtick",
      "line_number": 26,
      "suggested_fix": "`after-fence-flagged`"
    }
  ],
  "ok": false
}
EXIT=1
```

Notes on what is **NOT** flagged (intentionally):

- ``` ``foo`bar`` ``` — content contains a literal backtick,
  double form is required.
- ```` `` `` ```` — empty / whitespace-only span has separate
  CommonMark semantics.
- Triple-backtick spans like ```` ```triple``` ```` — out of
  scope; usually deliberate.
- Spans inside the fenced block — fences are skipped wholesale.
- The multi-line opening at the bottom of `input.md` — multi-
  line spans are out of scope.

## Files

- `detector.py` — pure-stdlib detector + JSON renderer + CLI
- `worked-example/input.md` — planted-issue input
- `worked-example/expected-output.txt` — captured exit + JSON
- `README.md` — this file

## Limitations

- The regex requires the entire span on one line. Multi-line
  inline code is permitted by CommonMark in some flavours but
  is fragile and rare; supporting it would force a stateful
  scanner. We accept the trade-off.
- We do not attempt to detect *unnecessary triple* backtick
  inline spans. The triple form for inline is so rare that
  catching it would mostly produce false positives on fence
  fragments mid-edit.
- The `suggested_fix` field is purely advisory. A consumer
  doing the rewrite should re-tokenize after the substitution
  to make sure no neighbouring backtick now binds to the
  shortened delimiter.
- Indented code blocks (4-space) are NOT skipped. They are
  rare in LLM output and would force a separate state machine;
  if your house style uses indented code blocks, layer an
  indented-block skip detector in front of this one.
