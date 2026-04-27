# llm-output-markdown-html-comment-unclosed-detector

## Problem

Markdown allows raw HTML, including comments:

```markdown
<!-- TODO: rewrite this section -->
```

If the closing `-->` is forgotten, every renderer (CommonMark, GFM, most
static-site generators) silently treats **everything from `<!--` to
end-of-file** as comment content. Headings disappear. Lists disappear.
Whole tail sections of the doc render as nothing — with no warning.

## When LLM output triggers it

- The model writes `<!-- begin draft note ...` intending to close it
  later, then loses track when streaming a long response.
- A multi-turn edit deletes the closing `-->` while keeping the opening
  `<!--`.
- The model emits a fenced code block whose example contains `<!--` and
  then forgets to close the fence, exposing the unclosed comment to the
  Markdown parser proper.

## Why it matters

- The failure mode is silent: docs render, just with chunks invisibly
  removed. No build error.
- For RAG indexing, the comment-eaten tail is often dropped before
  embedding too, so retrieval quality silently degrades.
- Reviewers reading raw Markdown often miss it because the prose looks
  fine in source.

## How the detector works

- Walks the document character-by-character with a small state machine:
  `outside-comment` ↔ `inside-comment`, switched by `<!--` and `-->`.
- Code-fence aware: fenced blocks (`` ``` `` / `~~~`) are skipped while
  not currently inside an open comment.
- Inline code spans (`` `<!--` ``) are stripped before scanning so that
  documentation about HTML comments doesn't false-positive.
- If the state machine ends in `inside-comment` after the last line, the
  position of the opening `<!--` is reported.

## Usage

```sh
python3 detect.py path/to/file.md
```

Exit codes: `0` clean, `1` unclosed comment found, `2` usage/IO error.

## Worked example

Run against `examples/bad.md`:

```
examples/bad.md:5:1: unclosed HTML comment '<!--' (no '-->' before EOF)
```

**1 finding**, exit 1. Run against `examples/good.md`: 0 findings,
exit 0.
