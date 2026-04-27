# llm-output-markdown-reference-link-undefined-label-detector

## Problem

Reference-style Markdown links and images point to a label that must be
defined elsewhere in the document:

```markdown
See [the docs][docs-link] for details.

[docs-link]: https://example.com/docs
```

When the definition is missing, the link renders as raw text like
`[the docs][docs-link]` — visually broken, no clickable target, no error
from most static-site generators (they silently leave it unlinked).

## When LLM output triggers it

- The model writes `[text][label]` mid-paragraph and forgets to append the
  `[label]: url` definition at the bottom.
- Multi-turn streaming truncates before the reference-definition block.
- The model uses the collapsed form `[Quickstart][]` and forgets that the
  link text itself becomes the label.
- Image references `![alt][fig]` are especially common — the model
  hallucinates a figure label that was never defined.

## Why it matters

- Silently broken links degrade documentation trust.
- Most lint pipelines miss this because raw rendering doesn't error.
- For docs ingested into RAG systems, the dangling label tokens add noise
  without semantic value.

## How the detector works

- Walks the document line-by-line, code-fence aware (`` ``` `` and `~~~`).
- Collects all definitions matching `^[ ]{0,3}\[label\]:\s*\S+`.
- Scans non-fenced, non-definition lines for `[text][label]` and
  `![alt][label]` (full + collapsed forms). Inline code spans are stripped
  before scanning so backtick-wrapped brackets don't false-positive.
- Labels are normalized per CommonMark: case-folded and internal whitespace
  collapsed.
- Shortcut form `[label]` (no second bracket pair) is intentionally **not**
  flagged — too many plain bracketed strings would false-positive.

## Usage

```sh
python3 detect.py path/to/file.md
```

Exit codes: `0` clean, `1` undefined labels found, `2` usage/IO error.

## Worked example

Run against `examples/bad.md`:

```
examples/bad.md:6:59: undefined reference label 'api' in [API reference][api]
examples/bad.md:7:42: undefined reference label 'Quickstart Guide' in [Quickstart Guide][]
examples/bad.md:9:37: undefined reference label 'arch-fig' in ![architecture diagram][arch-fig]
```

**3 findings**, exit 1. Run against `examples/good.md`: 0 findings, exit 0.
