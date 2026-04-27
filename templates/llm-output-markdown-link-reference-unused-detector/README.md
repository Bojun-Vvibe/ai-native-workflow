# llm-output-markdown-link-reference-unused-detector

## Problem

Markdown reference definitions look like this:

```markdown
[home]: https://example.com/
```

A definition is only useful if some `[text][home]`, `[home][]`, or
shortcut `[home]` actually consumes it. When an LLM streams a long
document, it frequently emits a tidy list of definitions at the bottom
that no longer matches what the prose links to — so you end up with
unused (orphan) definitions.

## When LLM output triggers it

- The model rewrites a paragraph mid-stream, removing a `[text][label]`
  reference, but never goes back to delete the now-orphan `[label]: url`
  definition.
- The model copies a "links section" boilerplate from a prior turn into a
  new doc whose body never uses those labels.
- A doc was trimmed for length and the body shrank, but the reference
  block at the bottom was left untouched.

## Why it matters

- Orphan definitions add noise for human readers scanning the bottom of
  the file and waste tokens for downstream prompts.
- Auto-formatters often reorder/preserve them, accreting cruft over many
  edits.
- For docs ingested into RAG, dangling URLs can be retrieved and cited
  for content that has nothing to do with them.

## How the detector works

- Walks the document line-by-line, code-fence aware (`` ``` `` and `~~~`).
- Pass 1: collect every `^[ ]{0,3}\[label\]: url` definition.
- Pass 2: scan non-fenced, non-definition lines for full-form
  `[text][label]`, collapsed `[text][]`, and shortcut `[label]` uses.
  Inline code spans are stripped first so backtick-wrapped brackets
  don't false-positive.
- Shortcut form is only counted as a use when a matching definition
  exists, so plain bracketed prose like `[see below]` doesn't masquerade
  as a reference.
- Labels are normalized per CommonMark: case-folded, internal whitespace
  collapsed.
- Reports any definition whose normalized label was never used.

## Usage

```sh
python3 detect.py path/to/file.md
```

Exit codes: `0` clean, `1` unused definitions found, `2` usage/IO error.

## Worked example

Run against `examples/bad.md`:

```
examples/bad.md:12: unused reference definition '[contributing]:'
examples/bad.md:13: unused reference definition '[license]:'
examples/bad.md:14: unused reference definition '[deprecated-spec]:'
```

**3 findings**, exit 1. Run against `examples/good.md`: 0 findings,
exit 0.
