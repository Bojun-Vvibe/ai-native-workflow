# llm-output-markdown-bare-url-without-autolink-detector

## Problem

A "bare URL" in Markdown is an `http://` or `https://` URL that appears
in prose without any wrapping syntax — neither `<...>` autolink form,
nor `[label](url)` inline-link form, nor a reference link.

In **strict CommonMark** (and many static-site generators, RAG
indexers, and PDF exporters) a bare URL is rendered as plain text. It
is not clickable. It cannot be tracked as a link by tooling. It does
not get a tooltip, does not get a link-rel pass, does not show up in
"outbound link" reports.

GitHub-Flavored Markdown does auto-linkify bare URLs, but documents
travel — a snippet that's clickable on github.com may render as inert
plain text on docs.example.com or in an offline PDF. The portable fix
is to wrap the URL in `<...>` so it becomes an autolink everywhere.

## When LLM output triggers it

- The model writes "see the spec at https://example.com/spec for
  details" because that's how URLs appear in its training prose.
- Streamed output completes a sentence with a URL just before
  punctuation (`...at https://example.com.`) and never goes back to
  wrap it.
- The model emits bullet lists where each item is `- Resource: <bare
  url>` because it learned that pattern from GitHub-rendered READMEs.

## How the detector works

- Walks the file line by line tracking fence state. Fenced code blocks
  (`` ``` `` and `~~~`) and inline code spans (`` `...` ``) are masked
  out so URLs inside code are not flagged.
- Reference link **definitions** (`[label]: https://...`) are skipped,
  because a definition is not a bare URL — it's the target of a
  reference link.
- For every remaining `https?://...` match, the detector checks
  whether the URL is already wrapped:
  - `<https://...>` autolink: the char before the URL is `<` and a `>`
    follows the URL with no whitespace between.
  - `[text](https://...)` inline link: the char before the URL is `(`
    and the char before that is `]`.
- Anything not wrapped is reported with line, column, the trimmed URL,
  and a suggested fix.
- Common trailing punctuation (`.`, `,`, `;`, `:`, `!`, `?`, `)`) is
  trimmed from the reported URL so a sentence-ending URL is shown
  cleanly.

## Usage

```sh
python3 detect.py path/to/file.md
```

Exit codes: `0` clean, `1` bare URL found, `2` usage / IO error.

## Worked example

Live run against the four bundled fixtures:

```
$ python3 detect.py examples/bad-prose.md examples/bad-trailing-punct.md examples/bad-in-list.md examples/good-wrapped.md
examples/bad-prose.md:3:17: bare URL 'https://example.com/spec' not wrapped as autolink (use <https://example.com/spec> or [text](https://example.com/spec))
examples/bad-prose.md:5:24: bare URL 'https://example.org/page-2' not wrapped as autolink (use <https://example.org/page-2> or [text](https://example.org/page-2))
examples/bad-trailing-punct.md:3:18: bare URL 'https://example.com/docs' not wrapped as autolink (use <https://example.com/docs> or [text](https://example.com/docs))
examples/bad-trailing-punct.md:5:20: bare URL 'https://example.org/release/v2' not wrapped as autolink (use <https://example.org/release/v2> or [text](https://example.org/release/v2))
examples/bad-in-list.md:3:17: bare URL 'https://example.com/one' not wrapped as autolink (use <https://example.com/one> or [text](https://example.com/one))
examples/bad-in-list.md:4:17: bare URL 'https://example.com/two' not wrapped as autolink (use <https://example.com/two> or [text](https://example.com/two))
examples/bad-in-list.md:6:23: bare URL 'https://example.org/background' not wrapped as autolink (use <https://example.org/background> or [text](https://example.org/background))
exit=1
```

Running `examples/good-wrapped.md` on its own (which exercises autolink,
inline-link, reference-link, inline-code, and fenced-code forms):

```
$ python3 detect.py examples/good-wrapped.md
exit=0
```

Counts: **3 bad fixtures** (7 findings total), **1 good fixture**
(0 findings).

## Relationship to the existing style-mix detector

`llm-output-markdown-autolink-bare-url-style-mix-detector` flags any
file that **mixes** autolink and bare-URL styles. This detector is
stricter: it flags **every** bare URL regardless of whether the file
also contains autolinks. Use the style-mix detector when you only care
about within-file consistency; use this one when you require autolink
form everywhere.
