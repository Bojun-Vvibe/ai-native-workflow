# llm-output-markdown-list-mixed-indent-detector

## Rule

Within a single Markdown document, nested list items should use a consistent
indentation unit. Mixing tabs, 2-space, and 4-space indents across sibling or
nested bullets makes rendering inconsistent across Markdown engines (CommonMark
expects 2 or 4 spaces; some renderers silently flatten tabs; LLMs frequently
mix all three in the same response).

This detector flags:

1. A list item indented with a **tab** when other items in the same document
   use spaces (or vice versa).
2. Sibling/nested bullets whose **space-indent unit is inconsistent** within
   the same document (e.g. one nested bullet uses 2 spaces and another uses
   4 spaces under siblings of the same parent depth).

Lines inside fenced code blocks (``` or ~~~) are ignored.

## Motivation

LLM Markdown output drifts between indentation styles when the model is
concatenating answers from differently-trained corpora. The rendered output
"looks" fine to the model but renders as broken nesting on GitHub, in IDE
preview, or in static-site generators. Catching this early avoids reflow bugs
in published docs.

## Usage

```
python3 detect.py <file.md>
```

## Exit codes

- `0` — no findings
- `1` — at least one finding (printed to stdout)
- `2` — usage error (missing/unreadable file)
