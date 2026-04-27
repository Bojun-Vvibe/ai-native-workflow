# llm-output-markdown-blockquote-trailing-empty-line-detector

Pure-stdlib Python 3 detector that flags markdown blockquote groups
ending with one or more "empty" `>` lines — that is, lines whose
content (after the `>` markers and the optional single space) is
whitespace-only.

## Failure mode

LLMs frequently "close" a blockquote by emitting an extra blank
quote line:

```text
> A real sentence.
> Another sentence.
>
>
```

The blockquote still parses, but most renderers either silently drop
the trailing empty `>` lines or render an extra paragraph break that
the author did not intend. The fix is to terminate the blockquote
with a true blank line (no `>`), or simply omit the trailing empty
`>` lines.

## What it detects

For each maximal run of consecutive blockquote lines, the detector
walks from the end and counts the trailing lines whose post-marker
content is whitespace-only. If that count is `>= 1`, it emits one
finding pointing at the first offending line of the trailing run.

Nested blockquotes are handled by stripping all leading `>` markers
before the emptiness check, so `> >` followed by `> >` followed by
`>` (where the `>` is empty) still flags.

## Why this is its own template

Sibling blockquote checks in this repo cover orthogonal failures:

- `llm-output-markdown-blockquote-empty-line-inside-detector` looks
  for empty `>` lines *between* non-empty quote lines (mid-quote
  gap), not the trailing-only pattern.
- `llm-output-markdown-blockquote-nested-marker-spacing-detector`
  covers `>>` vs `> >` spacing.
- `llm-output-markdown-blockquote-nesting-depth-validator` enforces
  a max depth.

None of them catch the trailing-empty-line pattern, which is its
own distinct LLM tic.

## Code-fence awareness

Lines inside ` ``` ` or `~~~` fenced code blocks are skipped
entirely. A literal `> ` line shown as a code example will not
trigger.

## Run it

```bash
python3 detector.py path/to/doc.md [more.md ...]
```

Output is `path:line: message`, one finding per line, followed by a
`summary: N finding(s)` line. Exit code is always `0`.

## Live worked example

Real, captured output from this template's bundled examples:

```text
$ python3 detector.py examples/bad.md
templates/llm-output-markdown-blockquote-trailing-empty-line-detector/examples/bad.md:7: blockquote ends with 2 trailing empty `>` line(s); strip them or terminate the blockquote with a blank line instead
templates/llm-output-markdown-blockquote-trailing-empty-line-detector/examples/bad.md:15: blockquote ends with 2 trailing empty `>` line(s); strip them or terminate the blockquote with a blank line instead
templates/llm-output-markdown-blockquote-trailing-empty-line-detector/examples/bad.md:21: blockquote ends with 1 trailing empty `>` line(s); strip them or terminate the blockquote with a blank line instead
summary: 3 finding(s)
```

```text
$ python3 detector.py examples/good.md
summary: 0 finding(s)
```

Three findings on the bad sample, zero on the good sample. The
fenced code block at the end of `bad.md` (which contains the very
offending pattern) does not flag, demonstrating fence awareness.
