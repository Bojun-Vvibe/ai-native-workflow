# llm-output-markdown-heading-blank-line-after-missing-detector

Detects ATX headings that are immediately followed by a non-blank, non-heading
line — i.e. the heading is butted up against its body content with no blank
line separator.

## Why this matters for LLM outputs

CommonMark renders `# H\nbody` correctly, so the page *looks* fine. But by
near-universal style convention (markdownlint MD022, remark-lint, prettier,
mdformat), an ATX heading should have a blank line after it. LLMs frequently
violate this when:

- The model emits the heading and starts the body in the same streamed turn
  without inserting the canonical blank line.
- A repair / merge pass joins two chunks and drops the separating blank line.
- The model imitates a "compact" style (common in some OSS READMEs) but does
  so inconsistently with the rest of its own output.

Downstream tooling that uses the blank line as a section delimiter — TOC
builders, retrieval chunkers, naive section splitters, diff-friendly
formatters — breaks on the missing separator, even though the rendered HTML
looks identical.

## What it does

- Streams the file line-by-line.
- Skips fenced code blocks (` ``` ` and `~~~`) so headings *inside* code are
  ignored.
- Matches ATX headings via `^ {0,3}#{1,6}(\s|$)` (CommonMark-compliant).
- For each heading, looks at the next line:
  - blank → ok
  - another ATX heading → ok (consecutive headings need no blank between)
  - EOF → ok
  - anything else → flag

## Run

```
python3 detect.py path/to/file.md
python3 detect.py examples/bad.md   # exits 1
python3 detect.py examples/good.md  # exits 0
```

Stdlib only, Python 3.8+.

## Verified worked example

Against `examples/bad.md` — exit `1`, **6 findings**:

```
examples/bad.md:3:1: heading-blank-line-after-missing (next_line='This paragraph starts immediately after the H1, with no blan')
examples/bad.md:6:1: heading-blank-line-after-missing (next_line='Run the installer and follow the prompts. Also bad — paragra')
examples/bad.md:9:1: heading-blank-line-after-missing (next_line='- list item that touches the H3 above. Bad.')
examples/bad.md:12:1: heading-blank-line-after-missing (next_line='> a blockquote touching an H4. Bad.')
examples/bad.md:15:1: heading-blank-line-after-missing (next_line='```')
examples/bad.md:22:1: heading-blank-line-after-missing (next_line='Body text after the deepest heading. Bad: H4 touches paragra')
```

Against `examples/good.md` — exit `0`, **0 findings** (no output).

## When to use

- As a CI lint on LLM-generated docs / READMEs / chat transcripts that round-
  trip through Markdown.
- As a pre-commit hook on agent-authored markdown to catch streaming join
  artifacts before review.
- As a diagnostic when retrieval chunkers or TOC builders start producing
  weird groupings on agent-written documents.

## Limitations

- ATX headings only. Setext headings (`===` / `---` underlines) are not in
  scope here — they have their own blank-line conventions handled by sibling
  detectors.
- Single-file scope; no cross-file aggregation.
- Report only; pair with a fixer that inserts a blank line after each flagged
  heading if you want auto-repair.
- Does not cover *blank-line-before* heading (handled by the existing
  `llm-output-markdown-blank-line-before-heading-consistency-validator`).
