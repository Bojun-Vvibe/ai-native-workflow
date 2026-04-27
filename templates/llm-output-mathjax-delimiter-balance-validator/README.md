# llm-output-mathjax-delimiter-balance-validator

## What it detects

Imbalanced or mismatched math delimiters in Markdown destined for a MathJax /
KaTeX renderer:

1. Odd count of inline `$ ... $` delimiters in a paragraph (one is unclosed).
2. Odd count of display `$$ ... $$` delimiters across the document.
3. Unmatched LaTeX-style brackets: `\(` without `\)`, `\[` without `\]`,
   or vice versa.
4. Nested or interleaved styles in a single paragraph (e.g. `\(foo$bar\)$`).

Math inside fenced code blocks (```` ``` ```` ... ```` ``` ````) and
inline code spans (`` ` ... ` ``) is ignored — those render literally.

## Why it matters

LLMs producing math notation regularly drop a closing delimiter, which causes
MathJax to swallow the rest of the paragraph (or document) into a math block,
producing garbled output that's hard to debug from the rendered page alone.
A pre-publish lint catches it instantly.

## Usage

```
python3 detector.py path/to/file.md
```

Exit codes:
- `0` — no findings
- `1` — at least one finding

Stdlib only.

## Algorithm

1. Strip fenced code blocks line-by-line.
2. Strip inline code spans (single, double, or triple backtick runs).
3. Count `$$` first (display math), then `$` (inline math) on the
   remaining text — escaping (`\$`) is honoured.
4. Independently count `\(` vs `\)` and `\[` vs `\]`.
5. Per-paragraph, ensure inline `$` count is even; per-document, ensure
   display `$$` count is even and bracket counts match.
