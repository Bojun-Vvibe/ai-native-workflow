# llm-output-markdown-setext-heading-underline-length-mismatch-detector

Flags **setext-style** markdown headings whose underline (`===` or
`---`) length does not match the heading text length.

## What it detects

A setext heading is two consecutive lines:

```
Heading Text
============
```

CommonMark only requires the underline to be at least one character,
but conventionally the underline matches the heading text length.
LLMs frequently emit underlines that are visually wrong (way too
short, way too long, or off by several chars), which:

- breaks downstream formatters that re-flow the underline
- looks "broken" in plain-text diffs
- is a strong signal the model lost track of the heading text

This detector flags any setext heading where
`abs(len(underline) - len(text)) > tolerance` (default tolerance: 0).

It is **code-fence aware**: setext-shaped lines inside fenced code
blocks (` ``` ` or `~~~`) are ignored.

## Why it matters for LLM-generated markdown

- Style consistency: enforces byte-stable headings across runs.
- Catches a common class of off-by-many errors where the model
  underestimates or overestimates the heading width.
- Surfaces accidental setext-vs-atx mixing (paired with the
  existing setext-vs-atx-heading-mix detector).

## Usage

```
python3 detect.py path/to/file.md
```

## Exit codes

| code | meaning |
| ---- | ------- |
| 0    | no findings |
| 1    | findings printed to stdout |
| 2    | usage error |

Output format: `<file>:<line>: setext underline length <u> != heading text length <t> (delta <d>)`

## Worked example

`examples/bad.md` contains 3 mismatched setext headings (one H1
underline too short, one H2 underline too long, and one inside a
list block); `examples/good.md` has only matched setext headings
plus a fenced block with intentionally mismatched lines that is
correctly ignored.
