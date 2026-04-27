# llm-output-html-comment-inside-fenced-code-detector

Pure-stdlib detector for **HTML comments leaking into fenced code
blocks** in LLM Markdown output.

## Why this exists

There is an adjacent template (`llm-output-html-comment-leak-detector`)
that flags `<!-- ... -->` in *prose*. This template is the dual: it
flags `<!-- ... -->` *inside* a fenced code block whose declared
language is **not** an HTML/XML/Markdown family.

LLMs do this when they conflate "this is a code comment" with "this is
a Markdown editorial comment". You see it in:

- Python / shell / Go / Rust / Java / SQL fences with a stray
  `<!-- TODO -->` that should have been `# TODO` or `// TODO`.
- JSON / YAML / TOML fences with `<!-- ... -->` (these langs have no
  comment syntax at all in JSON's case, and the line will fail to
  parse).
- Mixed-language explanations where the model shifts from explaining
  HTML in prose to writing Python and forgets to switch comment style.

Inside HTML/XML/Markdown/SVG/Vue/JSX fences, `<!-- -->` is legal, so
those are skipped.

## When to use

- Lint Markdown deliverables (READMEs, design docs, PR descriptions)
  produced by an LLM before they are committed.
- Wire into the same pre-commit pass as the prose leak detector;
  together they cover both "comment leaked into prose" and "comment
  leaked into wrong-language code".

## How to invoke

```
python3 detect.py path/to/output.md
```

Exit codes:

- `0` — clean, no findings.
- `1` — at least one finding.
- `2` — usage / IO error.

Output is a stable, sorted, line-oriented report:

```
<line>:<col> <kind> lang=<fence_lang> <snippet>
```

`kind` is one of:

- `html_comment_in_code` — a `<!-- ... -->` (single-line or
  multi-line) inside a fenced code block whose language is in the
  non-HTML denylist (or has no language tag).
- `unterminated_comment_in_code` — `<!--` opened inside a code fence
  and never closed before the closing fence or EOF.

Languages treated as **legal** for HTML comments (skipped):
`html`, `htm`, `xml`, `svg`, `xhtml`, `markdown`, `md`, `mdx`,
`vue`, `jsx`, `tsx`, `astro`, `liquid`, `handlebars`, `hbs`,
`mustache`, `ejs`, `nunjucks`, `jinja`, `jinja2`, `j2`, `erb`,
`razor`, `cshtml`, `php`, `aspx`.

## Worked example

`worked-example/bad.md` is a small Markdown blob with three offending
fences (python, json, sql) and one legal one (html). Running:

```
python3 detect.py worked-example/bad.md
```

should print exactly the lines in `worked-example/expected-output.txt`
and exit `1`.

## Non-goals

- Does not parse HTML. The matcher is a literal `<!--` … `-->`
  scanner, same as the prose-leak template.
- Does not flag `<!-- -->` inside *inline* code spans (`` `<!-- -->` ``).
  Inline code is intentionally short and is rarely where this leak
  pattern occurs; the prose detector still covers anything outside a
  fence.
- Does not try to suggest the correct comment syntax for the target
  language. The fix is always a one-line human edit.
