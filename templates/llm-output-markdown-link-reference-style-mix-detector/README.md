# llm-output-markdown-link-reference-style-mix-detector

Detects when a Markdown document mixes **inline** link syntax
(`[text](https://example.com)`) with **reference** link syntax
(`[text][ref]`, `[text][]`, or shortcut `[text]` paired with a
`[text]: url` definition).

LLM-generated Markdown frequently flips between the two styles within a
single document — sometimes paragraph-by-paragraph, sometimes
sentence-by-sentence. The two are semantically equivalent in HTML
output but visually inconsistent in source. This detector flags every
link occurrence and reports a `MIX DETECTED` failure when both styles
appear in the same file.

## What it does

- Walks the file line by line.
- Skips fenced code blocks (` ``` ` / ` ~~~ `) and inline code spans.
- Counts inline links (`[text](url)`) and reference links
  (`[text][ref]`, `[text][]`, shortcut `[text]`).
- Excludes link reference **definitions** (`[label]: url`) — those
  are not link *uses*.
- Excludes footnote references (`[^1]`).
- Exits 1 if both styles appear, 0 otherwise.

## Usage

```sh
python3 detect.py path/to/file.md
```

## Exit codes

| code | meaning                                       |
|------|-----------------------------------------------|
| 0    | clean — single link style (or zero links)     |
| 1    | mix detected — both styles present            |
| 2    | usage error                                   |

## Examples

```sh
# Bad: mixes inline and reference styles
python3 detect.py examples/bad.md ; echo "exit=$?"

# Good: only inline style
python3 detect.py examples/good.md ; echo "exit=$?"
```

## Output format

```
file: examples/bad.md
links found: 5 (inline=3, reference=2)
MIX DETECTED: document uses both inline and reference link styles
  line  3 [inline]: [Markdown spec](https://spec.commonmark.org)
  line  7 [reference-full]: [GitHub Flavored Markdown][gfm]
  ...
```

## Dependencies

Python 3 stdlib only.

## Limitations

- Does not chase whether shortcut references (`[text]`) actually
  resolve to a definition — any bracketed phrase that isn't followed
  by `(`, `[`, or `:` is counted as a reference-shortcut candidate.
  Use the `link-reference-definition-orphan-detector` for that.
- Image links (`![alt](src)`) are intentionally excluded.
