# llm-output-markdown-link-text-edge-whitespace-detector

Detect markdown links and images whose bracketed text has leading or
trailing whitespace inside the brackets.

LLMs often emit links as `[ click here ](https://x)` or
`[docs ](https://x/docs)` — the underlying phrase carried surrounding
spaces and the model wrapped brackets without trimming. CommonMark
preserves that whitespace, so the rendered link visibly underlines the
leading/trailing space, breaks anchor-text matching for analytics and
citation checkers, and trips markdownlint MD039.

## What it flags

- **Inline links**: `[text](url)` where `text` starts or ends with
  whitespace.
- **Inline images**: `![alt](url)` where `alt` starts or ends with
  whitespace.
- **Reference-style links**: `[text][ref]`, including collapsed
  `[text][]`.

For each finding the line, column, kind, and the offending text are
printed, with whether the issue is `leading`, `trailing`, or both.

## What it does NOT flag

- Empty link text `[](url)` — that is a separate finding class
  (covered by other validators).
- All-whitespace link text `[   ](url)` — same reason; it is empty
  text rather than edge-space.
- Anything inside fenced code blocks (` ``` ` or `~~~`) or inline code
  spans (`` `...` ``). Code is treated as literal.

## Why this matters

- **Visual rendering**: GitHub, most static-site generators, and most
  agent UIs underline the leading/trailing space, producing a hovering
  underline before/after the link text.
- **Accessibility**: screen readers announce the leading whitespace as
  a pause, which is wrong for a single anchor.
- **Tooling**: link-checkers, citation extractors, and analytics
  pipelines key on exact anchor text. `"Click here"` and
  `" Click here "` hash to different buckets.
- **Lint compatibility**: markdownlint MD039 forbids this exact
  pattern; this validator gives a stdlib-only equivalent for pipelines
  that cannot install Node.

## Usage

```
python3 script.py < your-doc.md
```

Exit code `1` on any finding (with one line per finding on stdout),
`0` on a clean document.

## Verify against the worked example

```
python3 script.py < worked-example/input.md | diff - worked-example/expected-output.txt
```

Should produce no diff. The script itself exits `1` because the input
contains five intentional findings (three inline links, one reference
link, one inline image). A clean companion file is also provided:

```
python3 script.py < worked-example/clean.md ; echo "exit=$?"
```

Should print `exit=0` with no other output.

## Implementation notes

- Pure Python 3 standard library, no third-party dependencies.
- Inline code spans are masked with spaces *before* link scanning so a
  literal `` `[ x ](url)` `` does not produce a false positive while
  column numbers in the surrounding text remain stable.
- Fenced code blocks are toggled on the standard `` ``` `` / `~~~`
  fence markers; nested or alternative fence syntax is not modeled.
- The link regex deliberately stops link-text at the first unescaped
  `]` and requires `(` immediately after, so nested or unbalanced
  brackets are skipped rather than mis-flagged.
