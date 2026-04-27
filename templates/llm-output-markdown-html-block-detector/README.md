# llm-output-markdown-html-block-detector

Flags **raw HTML block tags** that appear at the top level of a
markdown document outside of fenced code blocks.

## What it detects

LLMs frequently emit raw HTML blocks (`<div>`, `<table>`, `<p>`,
`<details>`, `<br>`, `<hr>`, `<img>`, etc.) inside what is supposed
to be plain markdown. While CommonMark technically allows HTML
passthrough, raw HTML blocks:

- break renderers that strip/escape HTML (GitHub issues, many
  static-site generators with `markdown_strict`)
- defeat downstream linting and accessibility tooling that expects
  semantic markdown
- are a strong signal the model "fell back" to HTML when it could
  not figure out a markdown construct (e.g., colspan tables,
  collapsible sections)

This detector flags any line that begins (after optional indent)
with one of the recognized HTML block-level open tags. It is
**code-fence aware**: HTML inside ` ``` ` or `~~~` blocks is
ignored. Inline HTML inside a paragraph (e.g., a sentence that
contains `<br>` mid-line) is **not** flagged — only block-leading
HTML.

HTML comments (`<!-- ... -->`) are also ignored; a separate
detector exists for those.

## Why it matters for LLM-generated markdown

- Portability: keeps output renderable in HTML-stripped contexts.
- Predictability: a downstream `markdown -> json` AST step won't
  silently produce `htmlBlock` nodes.
- Style: forces the model to commit to a markdown construct rather
  than escape into HTML.

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

Output format: `<file>:<line>: html-block tag <<tagname>>: <raw line>`

## Worked example

`examples/bad.md` contains 6 raw HTML block-leading lines (a
`<div>`, a `<table>` with a `<tr>`, a `<details>` with a
`<summary>`, and a self-closing `<hr/>`);
`examples/good.md` has the same content expressed in pure markdown
plus a fenced code block that contains HTML which is correctly
ignored, and an HTML comment that is also ignored.
