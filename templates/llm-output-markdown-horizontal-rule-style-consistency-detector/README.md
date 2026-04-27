# llm-output-markdown-horizontal-rule-style-consistency-detector

Detects when a single Markdown document mixes multiple horizontal-rule
(thematic-break) styles: `---`, `***`, and `___`.

## Rule

A document should use exactly one horizontal-rule style throughout. If two or
three styles appear in the same file, every occurrence is reported.

## Motivation

LLM-generated long-form Markdown is often stitched from multiple completions
or from training data with different style conventions. The CommonMark spec
treats `---`, `***`, and `___` as semantically identical thematic breaks, so
linters and humans alike rarely catch the inconsistency, but it makes
downstream diffs noisy and signals "machine-assembled" prose.

## Usage

```sh
python3 detector.py path/to/file.md
```

Run against the bundled example:

```sh
python3 detector.py bad.md
# matches expected-output.txt (sans the file-path prefix)
```

## Exit codes

| Code | Meaning |
| ---- | ------- |
| 0 | File uses zero or one HR style — clean. |
| 1 | Mixed HR styles detected; offending lines printed. |
| 2 | Usage error (missing file, etc.). |

## What it ignores

- Content inside fenced code blocks (``` and ~~~).
- Setext heading underlines (`---` immediately under a non-blank text line).
- Lines that are not pure HR candidates (e.g. `--foo`, `* item`).

## Limitations

- Does not enforce a *specific* preferred style — only consistency. Pair with
  a project policy file if you want to mandate `---`.
- Indented code blocks (4-space) are not currently excluded; prefer fenced
  blocks in inputs.
