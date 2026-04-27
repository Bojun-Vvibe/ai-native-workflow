# llm-output-markdown-paragraph-leading-indent-spaces-detector

Detect paragraph lines that start with 1, 2, or 3 leading space characters.
In CommonMark, a line indented by fewer than 4 spaces is still a regular
paragraph (4+ spaces would make it an indented code block) — but the source
is visually misleading, breaks many linters, and is almost always
unintentional in LLM-generated markdown.

Common cause: an LLM wraps prose around a list and indents follow-on
paragraphs to "align" them with the list text. The render looks fine but
the source is inconsistent with the rest of the document.

## What it flags

Every non-blank line that:

- Starts with 1, 2, or 3 space characters, AND
- Is not a list item, heading, blockquote, horizontal rule, table row,
  or setext underline, AND
- Is not inside a fenced code block.

## What it does not flag

- Lines starting at column zero
- Lines indented by 4 or more spaces (those are indented code blocks)
- Indented list items, headings, blockquotes, tables, HRs, setext underlines
- Lines inside ` ``` ` or `~~~` fenced code blocks
- Tab-indented lines (use a separate tab-indent detector for those)

## Usage

```
python3 script.py < your-doc.md
```

Exit code `1` if any flagged line is found, `0` otherwise.

## Verify against the worked example

```
python3 script.py < worked-example/input.md | diff - worked-example/expected-output.txt
```

Should produce no diff. The script itself exits `1` because the worked
example contains six intentional findings.
