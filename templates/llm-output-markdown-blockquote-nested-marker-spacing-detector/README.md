# llm-output-markdown-blockquote-nested-marker-spacing-detector

## Rule

Markdown nested blockquotes use repeated `>` markers. CommonMark requires a
space between adjacent markers and between the final marker and content,
e.g.:

```
> > nested quote
```

LLMs frequently emit:

- `>>nested` (no spaces between markers)
- `> >nested` (no space before content)
- `>>  nested` (two spaces before content; renders an indented code block in
  some engines)
- `>  > nested` (extra spaces between markers; some engines collapse, others
  break nesting)

This detector flags any nested-blockquote line whose marker spacing deviates
from the canonical `> > ... > content` pattern.

Lines inside fenced code blocks (``` or ~~~) are ignored.

## Motivation

Inconsistent marker spacing causes silent rendering drift across GitHub,
GitLab, Pandoc, and IDE preview panes. Detecting it at LLM-output time keeps
generated answers, code review comments, and docs renderable everywhere.

## Usage

```
python3 detect.py <file.md>
```

## Exit codes

- `0` — no findings
- `1` — at least one finding (printed to stdout)
- `2` — usage error (missing/unreadable file)
