# llm-output-markdown-blockquote-empty-line-inside-detector

## Problem

CommonMark terminates a blockquote when it encounters a fully blank line
(no `>` marker). To produce a multi-paragraph blockquote, the author must
insert a *bare* `>` line between paragraphs:

```markdown
> First paragraph.
>
> Second paragraph — same blockquote.
```

A fully blank line splits the quote into two adjacent quotes:

```markdown
> First paragraph.

> Second paragraph — NEW blockquote, with a visible gap.
```

## When LLM output triggers it

- The model imitates "regular paragraph spacing" inside a blockquote and
  emits a fully blank line where it should have emitted `>`.
- Reformatters / pretty-printers that strip "trailing whitespace lines"
  silently delete the bare-marker line, fragmenting the quote.
- Translation passes lose the lone `>` because it has no translatable
  content.

## Why it matters

- Two adjacent blockquotes render with a visible gap — looks like a layout
  bug to readers.
- Tools that parse blockquotes structurally (e.g. citation extractors,
  legal-doc pipelines) see two separate quotes and may attribute them to
  different sources.
- Search snippets pulled from the doc lose the multi-paragraph context.

## How the detector works

- Walks the document line-by-line, skipping fenced code regions
  (`` ``` `` / `~~~`).
- Marks each line as a blockquote line if it has 0–3 leading spaces
  followed by `>`.
- Flags any blank line whose *immediately previous* and *immediately next*
  non-fence lines are both blockquote lines — that's the fragmenting
  pattern.
- Bare `>` lines (the correct fix) are blockquote lines, not blank lines,
  so they don't trigger.

## Usage

```sh
python3 detect.py path/to/file.md
```

Exit codes: `0` clean, `1` fragmenting blank line(s) found, `2` usage/IO
error.

## Worked example

Run against `examples/bad.md`:

```
examples/bad.md:7: blank line between two blockquote lines fragments the quote; use '>' (a bare-marker line) to keep the quote continuous
examples/bad.md:14: blank line between two blockquote lines fragments the quote; use '>' (a bare-marker line) to keep the quote continuous
```

**2 findings**, exit 1. Run against `examples/good.md`: 0 findings, exit 0.
