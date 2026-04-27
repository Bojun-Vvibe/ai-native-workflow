# `llm-output-markdown-link-title-quote-style-consistency-detector`

Pure-stdlib detector for the LLM markdown failure mode where inline
link/image titles use inconsistent quote-wrap styles within one
document. CommonMark allows three title delimiters:

```
[text](url "double-quoted title")
[text](url 'single-quoted title')
[text](url (paren-wrapped title))
```

All three render identically. Mixing them inside one doc:

- breaks `markdownlint` `link-title-style` and Prettier's
  `--prose-wrap` style normalization,
- makes the raw source un-greppable for "every link with a title"
  (each style needs its own pattern),
- inflates diffs the moment any auto-formatter rewrites the minority
  style.

This detector is **independent** of the prose-quote validator
[`llm-output-quote-style-consistency-validator`](../llm-output-quote-style-consistency-validator/),
which looks at straight-vs-smart quotes in narrative text. This one
looks specifically at the **delimiter character around link/image
titles** inside `[text](url "title")` constructs.

## Finding kinds

Three kinds, sorted by `(offset, kind)` for byte-identical re-runs:

- `mixed_link_title_quote_style` — document uses more than one of
  `{double, single, paren}` for link/image titles. Reported once per
  minority-style title occurrence. The note field includes the full
  set of styles seen and the majority style, so a repair prompt is a
  single string interpolation away.
- `empty_link_title` — title delimiters are present but empty
  (`""`, `''`, `()`). These render as no-title and are almost always
  an LLM mistake (the model "remembered" titles need delimiters but
  forgot the content).
- `unbalanced_paren_title` — paren-style title where the inner
  paren depth never returns to zero before EOF. Defensive case for
  truncated outputs.

A document with zero or one quote style emits **nothing** (exit 0).
Links without titles are not findings — there's nothing to be
inconsistent about.

## Out of scope

- Whether the link target URL is reachable / well-formed.
- Reference-style links `[text][ref]` — they have no inline title.
- Autolinks `<https://...>` — they cannot have titles.
- HTML `<a title="...">` — separate parser concern.
- Prose typography (`"hello"` vs `“hello”`) — see
  [`llm-output-quote-style-consistency-validator`](../llm-output-quote-style-consistency-validator/).

Code spans (inline backticks and fenced blocks) are masked before
scanning so `[fake](url "x")` inside a code sample does not trigger.

## Usage

```sh
python3 detector.py path/to/file.md      # exit 1 on any finding
cat file.md | python3 detector.py -      # stdin mode
```

Output is one JSON object per finding line, e.g.

```json
{"col": 50, "kind": "mixed_link_title_quote_style", "line": 6, "note": "...", "offset": 195, "quote_style": "single", "title": "Reference index"}
```

JSON keys are sorted alphabetically so the stream is diff-stable.
`offset` is a 0-indexed byte offset into the source (after code
masking, but with column positions preserved). `line` and `col` are
1-indexed.

## Worked example

`examples/good.md` consistently uses `"..."` titles and includes a
fenced code block with a fake link inside (which is correctly
ignored). `examples/bad.md` mixes all three styles, contains an
empty `""` title, and exercises the masking on inline backticks.
`examples/expected-output.txt` is the byte that
`python3 detector.py examples/bad.md` produces; `good.md` exits 0 with
no output.

```sh
$ python3 detector.py examples/good.md ; echo $?
0
$ python3 detector.py examples/bad.md
{"col": 50, "kind": "mixed_link_title_quote_style", "line": 6, ...}
{"col": 40, "kind": "mixed_link_title_quote_style", "line": 7, ...}
{"col": 61, "kind": "empty_link_title",            "line": 11, ...}
$ echo $?
1
```

## When to wire this in

- **Pre-commit gate** on LLM-drafted README/docs files where the
  project pins a markdown formatter (Prettier, `mdformat`) — catch
  the mix at edit time so the formatter never has to rewrite half
  the file.
- **Review-loop step** for any agent that emits long-form
  documentation. Mixed link-title quote styles are a strong tell that
  the model concatenated outputs from different drafting passes.
- **Diff hygiene** in repos where doc PRs are reviewed by humans —
  one style means line-wise diffs reflect content changes, not
  formatter churn.
