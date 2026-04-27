# llm-output-markdown-emphasis-unmatched-asterisk-detector

Pure-stdlib Python 3 detector that flags markdown lines with an odd
parity-weighted count of `*` emphasis/strong delimiters — a strong
signal of unmatched emphasis (`*foo`) or strong (`**foo`) that
silently swallows the rest of the paragraph in most renderers.

## Failure mode

LLMs frequently emit prose like:

```text
This is *important and the model forgets to close it.
```

CommonMark won't render an emphasis pair, so the literal `*` shows
through; on a longer line the bug is invisible until it visibly
italicises everything until the next `*` (which may be paragraphs
later). Same for `**strong**` left half-open.

## What it counts

For each non-fenced, non-list-leader line:

1. Strip escaped `\*` (literal asterisks).
2. Strip balanced inline code spans (`` `…` ``).
3. Strip a leading list marker if the line starts with `* `.
4. Sum the lengths of all remaining `*` runs (consecutive `*`).
5. If that sum has odd parity, the line is reported.

A line of `*foo*` sums to `2` (even, OK). A line of `*foo` sums to
`1` (odd, flagged). A line of `**foo**` sums to `4` (even, OK). A
line of `***foo***` sums to `6` (even, OK).

## Why line-scoped

CommonMark emphasis cannot cross paragraph boundaries, so any real
emphasis pair must close on the same paragraph. Single-line parity
is the strictest, lowest-false-positive granularity. We deliberately
do not try to pair runs across lines — that would require a real
CommonMark parser and would add false positives around hard line
breaks.

## Why this is its own template

Sibling templates cover related but distinct concerns:

- `llm-output-markdown-bold-marker-style-consistency-detector` —
  `**` vs `__` style mixing.
- `llm-output-markdown-emphasis-marker-style-consistency-detector`
  — `*` vs `_` style mixing.
- `llm-output-emphasis-marker-consistency-validator` — same axis.
- `llm-output-markdown-emphasis-underscore-in-word-detector` —
  intra-word `_` ambiguity.

None of them count parity to find unmatched delimiters. This
template is the parity check.

## Code-fence awareness

Lines inside ` ``` ` or `~~~` fences are skipped wholesale. Inline
code spans (`` `like this` ``) are stripped before counting, so
`` `*not emphasis*` `` does not flag.

## Run it

```bash
python3 detector.py path/to/doc.md [more.md ...]
```

Output is `path:line: message`, one per finding, followed by a
`summary: N finding(s)` line. Exit code is always `0`.

## Live worked example

Real, captured output from this template's bundled examples:

```text
$ python3 detector.py examples/bad.md
templates/llm-output-markdown-emphasis-unmatched-asterisk-detector/examples/bad.md:3: unmatched `*` emphasis run on line (asterisk runs: [1], total parity odd)
templates/llm-output-markdown-emphasis-unmatched-asterisk-detector/examples/bad.md:5: unmatched `*` emphasis run on line (asterisk runs: [1, 1, 1], total parity odd)
templates/llm-output-markdown-emphasis-unmatched-asterisk-detector/examples/bad.md:7: unmatched `*` emphasis run on line (asterisk runs: [2, 2, 2, 2, 1], total parity odd)
summary: 3 finding(s)
```

```text
$ python3 detector.py examples/good.md
summary: 0 finding(s)
```

Three findings on the bad sample, zero on the good sample. The
fenced code block in `bad.md` (which contains the offending
pattern) does not flag, and inline-code asterisks plus escaped
asterisks in `good.md` are correctly ignored.

## Known limitations

- Even-parity lines with a real semantic mismatch (e.g. `*foo**`
  has runs `[1, 2]`, sum 3, odd — flagged correctly; but `**foo`
  has runs `[2]`, sum 2, even — *not* flagged) will be missed. This
  is the price of a stdlib heuristic. For full correctness, run a
  CommonMark parser; this template is a fast prefilter.
- Hard line breaks (`  \n`) are not modelled; emphasis crossing a
  hard break is rare in LLM output and would require a real parser.
