# llm-output-markdown-hard-tab-detector

Detects hard tab characters (`\t`, U+0009) in LLM-produced Markdown outside of
fenced code blocks. Equivalent to markdownlint rule **MD010 (no-hard-tabs)**.

## Why this matters for LLM outputs

LLMs sometimes emit literal tab characters when:
- copy-pasting from training data that used tabs for indentation,
- mixing markdown lists with tab-indented continuation lines,
- producing tables where they reach for `\t` instead of `|` separators.

Tabs render inconsistently across Markdown engines: GitHub renders a tab as
8 spaces, VS Code preview as 4, some renderers collapse them entirely.
A list item indented with a tab vs. four spaces can flip from a nested list
to a code block depending on the renderer. Catching tabs early prevents
silent layout drift.

## What it does

- Streams the input file line-by-line.
- Tracks fenced code block state (` ``` ` and `~~~`) so tabs *inside* fenced
  code are ignored — those are usually intentional (Makefiles, Go, TSV).
- Flags any other line containing `\t` and reports `path:line:col`.
- Exit code: `1` if any hard tab found outside code fences, else `0`.

## Run

```
python3 detect.py path/to/file.md
python3 detect.py examples/bad.md   # exits 1
python3 detect.py examples/good.md  # exits 0
```

Stdlib only, Python 3.8+.
