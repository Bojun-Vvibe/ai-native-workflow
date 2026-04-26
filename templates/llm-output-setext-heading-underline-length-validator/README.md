# `llm-output-setext-heading-underline-length-validator`

Pure-stdlib detector for **setext-style Markdown headings whose
underline is shorter than the heading text**:

```
My Heading
===

Subheading
--
```

CommonMark accepts any setext underline of length >= 1, so the
above renders as headings — but every renderer that does soft
visual alignment (most doc sites, GitHub preview, pandoc with a
typical template) leaves a stubby underline that looks like a
typo. It also signals that the LLM was counting characters
poorly, which correlates with other length-related drift
downstream (truncated table rows, off-by-one ordered lists).

Two finding kinds:

- `setext_underline_too_short_h1` — `=` underline shorter than
  the visible heading text length
- `setext_underline_too_short_h2` — same, but for `-` underline

The detector is deliberately conservative:

- Only flags when `len(underline) < len(text)`. Equal length
  is fine. Longer is fine.
- Heading text length is measured in **Unicode code points**
  after stripping leading/trailing whitespace. CJK width is
  NOT doubled — a 4-codepoint CJK heading just needs a 4-char
  underline, matching CommonMark's definition.
- The underline line must be **pure** `=`/`-` (with optional
  0-3 leading spaces and trailing whitespace). Anything else is
  not a setext underline.
- Fenced code blocks (` ``` ` and `~~~`) are skipped wholesale,
  so example Markdown in a tutorial does not self-trigger.
- A blank line between text and underline disqualifies setext
  per CommonMark; we honour that and do not flag.

## When to use

- Pre-publish gate on any LLM-generated **doc-site page**,
  **README**, **runbook**, or **release note** before merge.
  Stubby setext underlines are visually noisy and trivial to
  fix automatically once flagged.
- Inside a **review-loop validator**: each finding's
  `(heading_line_number, shortfall)` pair is small and
  deterministic, so the same finding twice across repair
  attempts is a clean "give up and escalate" signal.
- As a **prompt-template postcondition**: when a template
  pre-fills section titles, models often regenerate the
  underline at a fixed token length regardless of title
  length. This catches that drift.

## Usage

```
python3 detector.py [FILE ...]   # FILEs, or stdin if none
```

Exit code: `0` clean, `1` at least one finding. JSON to stdout.
Pure stdlib; no third-party deps.

## Composition

- `agent-output-validation` — feed the JSON `findings` array
  into a repair prompt verbatim. Each entry's
  `heading_text_length` and `underline_length` make the fix
  mechanical.
- `llm-output-heading-trailing-period-detector` — orthogonal:
  ATX headings have no underline, so the two detectors cover
  disjoint heading shapes. Run both for full heading hygiene.
- `llm-output-markdown-heading-skip-level-detector` — run
  after this one in a doc-quality pipeline; underline length
  is cheaper to fix than structural level skips, so failing
  fast on length tightens the repair loop.

## Worked example

Input is `worked-example/input.md` — planted issues across
both kinds, plus negative cases for equal-length, longer,
fenced-block-internal, and blank-line-separated underlines.

Actual end-to-end run, captured verbatim into
`worked-example/expected-output.txt`:

```
$ python3 detector.py worked-example/input.md
{
  "count": 6,
  "findings": [
    {
      "heading_line_number": 1,
      "heading_text": "My Heading",
      "heading_text_length": 10,
      "kind": "setext_underline_too_short_h1",
      "line_number": 2,
      "shortfall": 7,
      "underline_char": "=",
      "underline_length": 3
    },
    {
      "heading_line_number": 4,
      "heading_text": "Subheading",
      "heading_text_length": 10,
      "kind": "setext_underline_too_short_h2",
      "line_number": 5,
      "shortfall": 8,
      "underline_char": "-",
      "underline_length": 2
    },
    {
      "heading_line_number": 19,
      "heading_text": "Tight short H1",
      "heading_text_length": 14,
      "kind": "setext_underline_too_short_h1",
      "line_number": 20,
      "shortfall": 13,
      "underline_char": "=",
      "underline_length": 1
    },
    {
      "heading_line_number": 22,
      "heading_text": "A H2 with one dash",
      "heading_text_length": 18,
      "kind": "setext_underline_too_short_h2",
      "line_number": 23,
      "shortfall": 17,
      "underline_char": "-",
      "underline_length": 1
    },
    {
      "heading_line_number": 46,
      "heading_text": "Short After Fence Heading",
      "heading_text_length": 25,
      "kind": "setext_underline_too_short_h1",
      "line_number": 47,
      "shortfall": 16,
      "underline_char": "=",
      "underline_length": 9
    },
    {
      "heading_line_number": 49,
      "heading_text": "Final short one",
      "heading_text_length": 15,
      "kind": "setext_underline_too_short_h2",
      "line_number": 50,
      "shortfall": 12,
      "underline_char": "-",
      "underline_length": 3
    }
  ],
  "ok": false
}
EXIT=1
```

Notes on what is **NOT** flagged (intentionally):

- `Properly Underlined / ===================` — equal length.
- `Longer underline is also fine / ===========================` — longer is fine.
- The setext-shaped heading inside the fenced code block — fences are skipped wholesale.
- `Followup heading` after a blank line — the underline is full length.
- Plain prose mentioning `===` inside it — no underline shape.

## Files

- `detector.py` — pure-stdlib detector + JSON renderer + CLI
- `worked-example/input.md` — planted-issue input
- `worked-example/expected-output.txt` — captured exit + JSON
- `README.md` — this file

## Limitations

- We measure code-point length, not display width. Mixed
  CJK + ASCII headings will look slightly off-balance under a
  monospace renderer that double-widths CJK glyphs even when
  the underline matches code-point count. This is the same
  trade-off CommonMark itself makes; flagging on display width
  would require font metrics.
- We do not flag setext underlines that are *longer* than the
  heading text. Some house styles cap underline length at
  text length; that belongs in a separate "too-long" detector.
- We do not check that the underline is *exactly* the same
  length — only that it is not shorter. The "pretty alignment"
  question is style and out of scope.
- Indentation up to 3 spaces is allowed on the underline per
  CommonMark; 4+ spaces makes it a code block and we skip it.
