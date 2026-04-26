# `llm-output-markdown-blank-line-around-fenced-code-block-validator`

Pure stdlib validator for blank-line discipline around fenced code
blocks in LLM-generated Markdown — the bug class where the model
emits a fence with no blank line above (or below), the renderer
silently glues the fence into the surrounding paragraph, and the
result looks fine in some viewers but is broken in others.

CommonMark says a fenced code block does not strictly require a
blank line before it, but the *practical* rule (enforced by
`markdownlint` rule MD031, by Prettier, by every static-site
generator that runs Markdown through a paragraph parser first, and
by GitHub's renderer when the surrounding paragraph is non-trivial)
is that fences need breathing room. When they don't get it:

- GitHub silently renders the fence as a literal triple-backtick
  string inside the preceding paragraph instead of as code.
- RAG chunkers that split on blank lines glue prose and code into
  one chunk that the embedder cannot tag (the "is this a paragraph
  or a code sample?" signal is gone).
- `pandoc` and most static-site generators emit a different (and
  less-readable) HTML structure — `<p><code>...</code></p>`
  instead of `<pre><code>...</code></pre>`.
- Copy-the-code-block UI affordances on doc sites silently fail
  because the parser never registered a code block at all.

Four finding kinds, all per-fence:

- `missing_blank_before` — fence opener immediately follows a
  non-blank line that is not itself a fence opener and not a list
  item (when `allow_in_list_item=True`, the default).
- `missing_blank_after` — fence closer is immediately followed by
  a non-blank line.
- `unclosed_fence` — fence opens and reaches end of input without a
  matching closer. Well-known failure mode of LLMs that hit
  `max_tokens` mid-code-block.
- `mismatched_fence_char` — fence opens with ```` ``` ```` but a
  candidate closer in the body uses `~~~` (or vice versa). The
  closer is silently treated as code body, so the next paragraph
  becomes part of the block.

The fence parser is CommonMark-correct: opener is a run of ≥3 of
the same char (`` ` `` or `~`), with indent ≤3 spaces, optional
info string after; closer must be the same char, run length ≥
opener's run length, and have no info string after the run. This
matters for the mismatched-char case — a `~~~` line inside a
backtick-fenced block is structurally code body, but flagging it as
a smell catches the model that intended to close.

## When to use

- Pre-publish gate on any LLM-generated **README**, **runbook**, or
  **PR description** that contains code blocks. The bug is
  invisible in GitHub's preview when the surrounding paragraph is
  short, and it ships unnoticed.
- Post-generation hook on **agent-authored documentation** before
  it lands in a knowledge base. RAG chunkers that split on blank
  lines mis-bucket every "fence-glued-to-prose" output.
- Audit step in a **review-loop** that promotes
  [`agent-output-validation`](../agent-output-validation/)'s
  `repair_once` policy: a `missing_blank_before` /
  `missing_blank_after` finding feeds the offending line numbers
  back into the repair prompt with one instruction (`"insert a
  blank line above and below every fenced code block"`).
- Cron-friendly: findings are sorted by `(line_no, kind)`, the
  report is byte-identical across runs, diff-on-the-output is a
  valid CI signal.

## Inputs / outputs

```
validate_fence_blank_lines(
    text: str,
    *,
    allow_in_list_item: bool = True,
) -> list[Finding]

Finding(kind: str, line_no: int, detail: str, sample: str)
```

- `text` — the Markdown to scan. Must be `str` (raises
  `ValidationError` otherwise).
- `allow_in_list_item` — when `True` (default), a fence whose
  opener immediately follows a list-item line (`- `, `* `, `+ `,
  `1. `, `1) `) is exempt from the `missing_blank_before` check
  (this is the canonical Markdown idiom for "code sample inside
  this list item"). Set to `False` for projects that want the
  blank line even there.
- `Finding.line_no` is 1-based and points at the offending
  fence-related line in the source. For `missing_blank_after`
  it points at the closer; for `unclosed_fence` and
  `missing_blank_before` it points at the opener.
- `Finding.sample` carries the offending line verbatim (trailing
  newline stripped) so the report is self-contained.
- `format_report(findings)` renders a deterministic plain-text
  report. Empty list →
  `"OK: fenced code blocks have proper blank-line discipline.\n"`.

Pure function: no I/O, no markdown library, no regex backtracking.
Only state is a tiny per-fence scan (opener char, run length, and
the running mismatched-char list within the body).

## Composition

- [`agent-output-validation`](../agent-output-validation/) — feed a
  finding's `(kind, line_no)` into the repair prompt for a one-turn
  fix; this template is the validator behind the `repair_once`
  policy for prose outputs that contain fenced blocks.
- [`llm-output-markdown-heading-level-skip-detector`](../llm-output-markdown-heading-level-skip-detector/),
  [`llm-output-markdown-ordered-list-numbering-monotonicity-validator`](../llm-output-markdown-ordered-list-numbering-monotonicity-validator/),
  [`llm-output-list-marker-consistency-validator`](../llm-output-list-marker-consistency-validator/),
  [`llm-output-code-fence-language-tag-validator`](../llm-output-code-fence-language-tag-validator/) —
  orthogonal sibling Markdown-hygiene gates. Same `Finding`-shape
  pattern and stable sort, so a single CI step can union their
  findings into one report. The language-tag validator and this
  validator together cover the two dimensions of fence quality:
  *what's tagged on the fence* vs *how the fence sits in the doc*.
- [`llm-output-fence-extractor`](../llm-output-fence-extractor/) —
  orthogonal: that template extracts fenced blocks for downstream
  consumption, this template validates their *placement*. Run this
  first as a gate; if it passes, the extractor's output is safer.
- [`model-output-truncation-detector`](../model-output-truncation-detector/) —
  the `unclosed_fence` finding is the strongest single signal of a
  `max_tokens`-truncated generation. The two validators agree on
  the failure but report from different angles; if both fire, route
  to the truncation-recovery flow.
- [`structured-error-taxonomy`](../structured-error-taxonomy/) —
  `missing_blank_before` / `missing_blank_after` /
  `mismatched_fence_char` classify as `do_not_retry /
  attribution=model`; `unclosed_fence` is special — almost always
  `attribution=infrastructure` (token cap), retry with a higher
  cap or a continuation prompt rather than a corrective system
  message.

## Worked example

```
$ python3 example.py
```

Verbatim output:

```
=== 01-clean ===
input:
  | Here is a code sample:
  | 
  | ```python
  | print('hi')
  | ```
  | 
  | More prose.
OK: fenced code blocks have proper blank-line discipline.

=== 02-missing-blank-before ===
input:
  | Here is a code sample:
  | ```python
  | print('hi')
  | ```
  | 
  | More prose.
FOUND 1 fence finding(s):
  [missing_blank_before] line=2 :: fence opener has no blank line above; prior line 1 is non-blank prose (renderers may glue the fence into the preceding paragraph)
    | ```python

=== 03-missing-blank-after ===
input:
  | Here is a code sample:
  | 
  | ```python
  | print('hi')
  | ```
  | More prose.
FOUND 1 fence finding(s):
  [missing_blank_after] line=5 :: fence closer has no blank line below; line 6 is non-blank (renderers may glue following content into the code block)
    | ```

=== 04-unclosed-fence ===
input:
  | Intro paragraph.
  | 
  | ```python
  | print('hi')
  | print('bye')
FOUND 1 fence finding(s):
  [unclosed_fence] line=3 :: fence opened with '```' at line 3 but no matching closer found before end of input
    | ```python

=== 05-mismatched-fence-char ===
input:
  | Intro.
  | 
  | ```python
  | print('hi')
  | ~~~
  | print('still in block')
  | ```
  | 
  | Outro.
FOUND 1 fence finding(s):
  [mismatched_fence_char] line=5 :: line uses '~' fence char inside a block opened with '`' at line 3 (treated as code body; if a closer was intended the block extends past where you meant)
    | ~~~

=== 06-list-item-exemption ===
input:
  | Steps:
  | 
  | - Run this command:
  |   ```bash
  |   ./deploy.sh
  |   ```
  | - Verify output.
FOUND 1 fence finding(s):
  [missing_blank_after] line=6 :: fence closer has no blank line below; line 7 is non-blank (renderers may glue following content into the code block)
    |   ```

=== 07-double-bad ===
input:
  | Prose intro.
  | ```python
  | print('first')
  | ```
  | Middle prose with no breathing room.
  | ```python
  | print('second')
  | ```
  | Outro.
FOUND 4 fence finding(s):
  [missing_blank_before] line=2 :: fence opener has no blank line above; prior line 1 is non-blank prose (renderers may glue the fence into the preceding paragraph)
    | ```python
  [missing_blank_after] line=4 :: fence closer has no blank line below; line 5 is non-blank (renderers may glue following content into the code block)
    | ```
  [missing_blank_before] line=6 :: fence opener has no blank line above; prior line 5 is non-blank prose (renderers may glue the fence into the preceding paragraph)
    | ```python
  [missing_blank_after] line=8 :: fence closer has no blank line below; line 9 is non-blank (renderers may glue following content into the code block)
    | ```

```

Notes:

- Case 02 — the most common shape of the bug: a colon-introducing
  paragraph (`Here is a code sample:`) directly followed by the
  opener with no blank line. The detail string explicitly names
  the line number of the prior non-blank line so a reviewer reading
  the report alone has enough to fix it.
- Case 03 — the mirror: closer followed immediately by `More prose.`
  on the next line. Most renderers tolerate this but `pandoc` and
  several static-site generators silently extend the code block to
  include the following paragraph.
- Case 04 — opener at line 3, no closer reaches end of input.
  Strongest single signal of a `max_tokens`-truncated generation.
  The detail spells out the opener's char-and-run-length
  (`'\`\`\`'`) so a continuation prompt can be built mechanically.
- Case 05 — the block opens with `` ``` ``, then a `~~~` line in the
  middle. The `~~~` is *structurally code body* per CommonMark
  (mismatched char), but it's almost always a model artifact — the
  generator switched fence styles mid-output. We surface it as a
  smell with an explicit warning that the block "extends past where
  you meant"; the closer at line 7 is the real closer, the `~~~`
  was meant to be it.
- Case 06 — a fence inside a list item. The opener (line 4) follows
  a list item (`- Run this command:`) so the list-item exemption
  fires and `missing_blank_before` is suppressed. The closer (line
  6) is followed by another list item (`- Verify output.`) — that
  *is* a bug because the closer needs the blank line regardless of
  the list context to make the list-item structure unambiguous, so
  `missing_blank_after` is correctly reported. This proves the
  exemption is one-sided and intentional.
- Case 07 — two fences back to back with no breathing room and a
  middle paragraph. Four findings, sorted by line number, in order:
  before-1, after-1, before-2, after-2. The deterministic sort makes
  the report diffable.

## Files

- `validator.py` — pure stdlib validator + `format_report`
- `example.py` — seven worked-example cases (run: `python3 example.py`)
- `README.md` — this file

## Tuning

- `allow_in_list_item=False` is the strict mode for projects that
  enforce blank-line-before-fence even inside list items (Prettier
  defaults to this; `markdownlint` MD031 has a config flag for it).
  Most LLM output is bound for GitHub-flavored Markdown rendering
  where the default `True` matches the practical rule.
- No threshold parameters — the four findings are categorical and
  the fix in each case is mechanical.

## Limitations

- The validator handles symmetric fences (`` ``` `` and `~~~`) per
  CommonMark. It does NOT handle indented code blocks (the
  4-space-indent kind) — those are a different syntax with
  different blank-line rules and the LLM-output failure mode for
  them is much rarer.
- The list-item exemption recognizes only the standard list-item
  shapes (`-`, `*`, `+`, `\d+.`, `\d+)`). A fence inside a
  blockquote (`>`) or a definition-list item is not exempted; the
  validator will flag the missing blank line. This is intentional
  conservatism — those contexts are rare in LLM output, and when
  they do occur the blank-line rule still applies.
- For the `unclosed_fence` case the validator stops scanning at end
  of input and does not look for fences after the unclosed one (any
  later content is, by CommonMark, code body of the unclosed
  block). This means a doc with multiple unclosed fences reports
  only the first; that's the correct CommonMark interpretation, not
  a parser limitation.
