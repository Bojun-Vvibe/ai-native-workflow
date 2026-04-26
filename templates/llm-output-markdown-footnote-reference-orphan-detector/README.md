# llm-output-markdown-footnote-reference-orphan-detector

Detect orphaned and duplicated markdown footnotes in LLM-generated text.

## Purpose

Large language models frequently invent footnote references like `[^src1]`,
`[^study]`, or `[^a]` without ever providing the corresponding definition
`[^src1]: ...`, or define footnotes that nothing in the prose actually
points at. This template scans markdown content and surfaces three failure
modes:

1. **Refs without definitions** — `[^id]` appears in the body, but no
   `[^id]: ...` line exists. Reader is left with a dangling marker.
2. **Defs without refs** — a `[^id]: ...` definition exists but is never
   referenced. Usually a leftover from a hallucinated cite the model later
   removed.
3. **Duplicate definitions** — the same footnote id is defined more than
   once. Most renderers silently keep one and drop the rest.

Fenced code blocks (` ``` ` and `~~~`) are stripped before scanning so that
example footnote syntax inside a code sample doesn't trigger false positives.

## Inputs

- A markdown document, either:
  - Passed as a file path: `python3 check.py path/to/doc.md`
  - Or piped via stdin: `cat doc.md | python3 check.py`

## Outputs

- Plain-text report on stdout listing counts and the offending ids.
- Exit code `0` if clean, `1` if any issue was found.
- No external dependencies — Python 3 stdlib only.

## When to use

- Pre-commit hook on AI-drafted documentation, research notes, or blog posts.
- CI gate on long-form LLM output (RAG answers, report generators) that is
  allowed to use footnotes.
- One-off audit of a corpus of generated markdown.

## Worked example

Fixture (`/tmp/fn_fixture.md`):

```markdown
# Sample doc

This claim has a source[^src1] and another[^src2]. Also see[^missing-one].

Here's a code block that mentions [^not-a-ref] which should be ignored:

```
[^not-a-ref]: this is inside code, ignore me
```

[^src1]: First source.
[^src2]: Second source.
[^src2]: Duplicate of src2.
[^unused]: Nobody references this.
```

Note: in the fixture above, the prose line *outside* the fence still
mentions `[^not-a-ref]`, so that id is legitimately flagged as a ref
with no definition (the would-be definition is hidden inside a code
block and therefore ignored, which is the intended behavior).

Command:

```
python3 templates/llm-output-markdown-footnote-reference-orphan-detector/check.py /tmp/fn_fixture.md
```

Actual output:

```
footnote refs found:       4
footnote defs found:       4
refs without definition:   ['missing-one', 'not-a-ref']
defs without reference:    ['unused']
duplicate definitions:     ['src2']
status: FAIL (4 issue(s))
exit=1
```

The detector correctly identifies the dangling reference `missing-one`,
the orphan definition `unused`, and the duplicate definition for `src2`.

## Limitations

- Treats any `[^id]` outside fenced code as a real reference; inline code
  spans (single-backtick) are not stripped.
- Only the standard kebab/underscore footnote id charset is recognized
  (`A-Za-z0-9_-`). Exotic ids with unicode are not detected.
- Does not validate the body of definitions (empty defs are allowed).
