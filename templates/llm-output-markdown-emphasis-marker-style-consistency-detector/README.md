# llm-output-markdown-emphasis-marker-style-consistency-detector

Detects when a single Markdown document mixes single-marker emphasis styles
(`*italic*` and `_italic_`) for italics.

## Rule

A document should pick one italic-emphasis marker (`*` or `_`) and use it
consistently. When both appear, every occurrence is reported, with the
majority and minority style called out.

This detector is scoped to *single-marker* emphasis only. Bold (`**` / `__`)
is ignored — that lives in a separate detector.

## Motivation

Both markers render identically. Mixing them is a textbook LLM stitching
artifact: one completion uses `*` and the next uses `_`. The mix never breaks
rendering, so it slips through normal review, but it makes diffs noisy and
signals the document was not human-edited end to end.

## Usage

```sh
python3 detector.py path/to/file.md
```

Run against the bundled example:

```sh
python3 detector.py bad.md
# matches expected-output.txt (sans the file-path prefix)
```

## Exit codes

| Code | Meaning |
| ---- | ------- |
| 0 | Consistent (only one style, or fewer than 2 spans). |
| 1 | Mixed styles detected. |
| 2 | Usage error. |

## What it ignores

- Fenced code blocks (``` and ~~~).
- Inline code spans (`` `...` ``).
- Bold markers (`**` / `__`).
- Intra-word underscores like `snake_case_name` (regex anchored on word
  boundaries).

## Limitations

- Does not flag a document that uses only `_` or only `*` — it only flags
  *mixing*. Pair with a project policy doc to mandate a specific marker.
- Indented (4-space) code blocks are not excluded; prefer fences in inputs.
