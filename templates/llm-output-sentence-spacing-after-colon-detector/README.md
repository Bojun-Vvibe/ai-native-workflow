# `llm-output-sentence-spacing-after-colon-detector`

Pure-stdlib detector for inconsistent or pathological spacing
after a `:` colon in an LLM Markdown / prose output blob.

## The bug class

LLM outputs routinely mix three different colon-spacing
conventions in the same document:

- `label: value` — one space after the colon. Standard prose.
- `label:value` — zero space. Leaks from JSON-shaped sources or
  from a stop-token cut mid-stream.
- `label:  value` — two-or-more spaces (or a tab). Leaks from a
  fixed-width / aligned-table source the model was trained on.

Each convention is fine on its own. Mixing them in the same blob
is a tell that the model concatenated chunks from different
sources mid-generation, and is invisible in HTML render but loud
in the source bytes, in `git diff`, and in any field-extraction
regex downstream.

## What is excluded

Colons inside the following are ignored — they are not prose
colons:

- URL schemes: `https://`, `git://`, `file:/` (any `:` immediately
  followed by `//`).
- Times and ratios: `12:30`, `1:1` (any `:` flanked on both sides
  by ASCII digits).
- Inline code spans: `` `key:value` `` (the entire backtick span
  is masked before colon scanning).
- Fenced code blocks (` ``` ` … ` ``` ` or `~~~` … `~~~`) — every
  line inside the fence is skipped.
- Trailing colons at end of line — these are list/heading
  lead-ins (`Notes:` followed by bullets on the next line), not
  inline label-value separators, and have no spacing to check.
- Symbols like `::`, `:)`, `:-)` — the post-colon character must
  be alphanumeric or an opening quote/bracket to count as a
  prose colon.

## Finding kinds

- `mixed_colon_spacing` — the document uses MORE THAN ONE
  convention (any two of {0-space, 1-space, 2+-space} both
  appear). Reported once, scope=blob, with the per-convention
  inventory. Emitted FIRST so a reviewer sees the distribution
  before the per-line noise.

- `excess_space_after_colon` — a run of 2+ spaces, or any tab,
  after a colon. Always reported per occurrence. A 2+ run after
  a prose colon is never legitimate — it is either an alignment
  artifact or a model that lost track of its own style.

- `zero_space_after_colon_in_one_space_blob` — a 0-space colon
  in a blob whose majority is 1-space. Reported per occurrence
  with line and column.

A blob whose majority is 0-space (e.g., a YAML-shaped doc) does
not get the symmetric finding — the detector assumes prose
intent. If the doc is genuinely YAML, it should be inside a
fenced block and skipped entirely.

## When to use

- Post-process every long-form LLM Markdown answer before
  shipping to a human reader.
- As a CI lint on docs an agent edits, especially when those
  docs mix narrative prose and key:value summaries.

## When NOT to use

- On structured-data files (YAML, INI, HTTP headers) that
  legitimately use a single non-prose colon convention. Either
  fence those, or run the detector on the prose-only portion.
- On i18n content where the colon is fullwidth (`：`, U+FF1A) —
  this detector only matches ASCII `:`. A separate fullwidth
  detector is appropriate for CJK contexts.

## Input

Reads UTF-8 text from stdin or a path argument:

```
python3 detect.py < input.md
python3 detect.py path/to/file.md
```

## Worked example

`example_input.txt`:

```
Summary: this paragraph mixes colon styles on purpose.
Name: Alice (one-space — fine).
Role:engineer (zero-space — leak from JSON).
Status:  active (two-space — leak from aligned table).
Notes:	indented with a tab (also two-or-more bucket).

URL example: see https://example.com/path — colon in scheme is ignored.
Time example: meeting at 12:30 today — digit-flanked colon ignored.
Trailing colon at end of line:
- bullet item one
- bullet item two

Inline `key:value` inside a code span is ignored, even though the
surrounding prose has a colon: like this one (one-space).

```yaml
key:value
key:    value
key: value
```

After the fence: the doc continues; this colon is one-space.
```

Run:

```
python3 detect.py < example_input.txt
```

Verbatim stdout:

```
FAIL: 4 finding(s).
  blob: mixed_colon_spacing zero=1 one=6 two_or_more=2
  L3 col 5: zero_space_after_colon_in_one_space_blob
  L4 col 7: excess_space_after_colon (run=2)
  L5 col 6: excess_space_after_colon (tab)
```

Exit code: `1` (findings present).

Confirm by inspection:

- L3 `Role:engineer` — zero-space, minority. Flagged.
- L4 `Status:  active` — two spaces. Flagged.
- L5 `Notes:	indented` — tab. Flagged.
- L7 `https://...` colon in URL scheme — silently passed.
- L8 `12:30` time — silently passed.
- L9 `Trailing colon at end of line:` — silently passed.
- L13–14 colon inside `` `key:value` `` — silently passed.
- L17–19 colons inside the fenced YAML block — silently passed.
- L21 `After the fence:` — one-space, majority. Silently passed.

The blob inventory `zero=1 one=6 two_or_more=2` confirms 1-space
is the majority, and the per-occurrence findings exactly match
the three deliberately-bad lines.

## Files

- `detect.py` — pure-stdlib detector
- `example_input.txt` — the worked-example input above
- `README.md` — this file

## Limitations

- The detector treats a tab after a colon as "2+ space bucket"
  rather than reporting "tab" as its own kind. The per-finding
  output does mark `(tab)` so the reviewer knows the difference.
- Inline-code masking pairs backticks by length on a single
  line. An unclosed inline-code span on a prose line will leave
  its colons exposed to the detector. That is the correct
  behavior — the unclosed-backtick bug should be caught
  separately by
  [`llm-output-inline-code-backtick-balance-detector`](../llm-output-inline-code-backtick-balance-detector/),
  and an unclosed span has no defensible colon-spacing semantics
  anyway.
- Fence detection looks at the first non-whitespace characters
  of the line. A fence indented inside a deeply-nested list item
  follows the same rule.
- The detector does NOT attempt repair. The mechanical fix for
  the majority-convention case is
  `re.sub(r':[ \t]{2,}', ': ', text)` for excess space and the
  symmetric per-line patch for zero-space leaks.
- Empty input returns "OK" with exit 0.
