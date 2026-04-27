# llm-output-markdown-autolink-malformed-scheme-detector

## Problem

CommonMark autolinks have the form `<scheme:rest>` and require a valid
URI scheme: a letter followed by `[A-Za-z0-9+.-]{1,31}`, then a colon.
Examples: `<https://example.com>`, `<mailto:a@b.io>`.

LLMs frequently emit autolink-shaped tokens whose "scheme" portion is
malformed:

- Missing scheme: `<://example.com>`
- Scheme starts with a digit: `<3http://example.com>`
- Scheme contains an underscore or space: `<weird_scheme:foo>`,
  `<my scheme:foo>`
- Scheme is empty before the colon: `<:relative>`
- Scheme has a trailing dot or repeated colons: `<http.:foo>`,
  `<https::example.com>`

CommonMark renderers do **not** linkify these. They render literally as
`<://example.com>`, which (a) leaks angle brackets into prose, and
(b) silently strips clickable navigation that the model intended.

## Why it matters

- Silent UX regression: the doc looks intentional in source review but
  ships dead links/decoration.
- For RAG and link-checkers, the URL is invisible because it never
  becomes a link node in the AST.
- For mail-merge / `mailto:` output, malformed schemes mean the user's
  mail client never opens.

## Detection rule

A token of the shape `<...>` on a single line is treated as a candidate
autolink when:

- It contains `:` before the closing `>`.
- It contains no whitespace inside the brackets.
- It is not inside a fenced code block or inline code span.

For each candidate, the substring before the first `:` is the scheme.
The detector flags the candidate when the scheme does **not** match the
CommonMark autolink scheme grammar:

```
scheme := [A-Za-z][A-Za-z0-9+.-]{1,31}
```

It also flags the empty-scheme case (`<:rest>`) and the no-scheme
double-slash case (`<//host>`, `<://host>`) which the model usually
intends as a URL.

## False-positive notes

- Real HTML tags such as `<br>`, `<img src="...">`, `<a href="...">`
  are skipped because they either contain whitespace, contain `=`, or
  do not contain a colon before `>`.
- Generic-typed placeholders like `<List<int>>` contain no colon and
  are skipped.
- Email autolinks (`<user@host>`) contain no colon and are not handled
  by this lens; they have their own validity rules.
- Anything inside fenced (` ``` ` / `~~~`) or inline (`` ` ``) code is
  skipped so that documentation showing bad autolinks does not trip
  the detector.

## Usage

```sh
python3 detector.py path/to/file.md [more.md ...]
```

Exit codes: `0` clean, `1` malformed autolink found, `2` usage/IO
error.

## Worked example

`examples/bad/` contains three files, each exhibiting a different
malformation. `examples/good/clean.md` exercises every legal scheme
shape this lens accepts and must report 0 findings.
