# llm-output-link-reference-definition-orphan-detector

Pure-stdlib validator for the LLM-Markdown failure mode where the
output uses *reference-style* links (`[text][label]`, `[text][]`,
`[label]`) and the link / definition table goes out of sync — most
commonly because the generator was truncated before the definitions
block, an edit removed the prose but left the definition, or the
model emitted two definitions for the same label from two different
recalled sources.

## Why this exists

Reference-style links are popular in LLM output because they keep
prose readable and let the model emit URLs in a separate block. The
failure modes are subtle:

- **`undefined_reference`** — the prose says `[runbook][runbook]`
  but no `[runbook]: <url>` exists. GitHub renders this as literal
  square-bracket prose; pandoc emits an empty `<a href>`; some
  static-site generators raise a build error. The model often
  produces this when the definitions block was truncated, or when it
  imagined a reference list that never made it to the output.
- **`orphan_definition`** — `[label]: <url>` exists but no reference
  uses it. The doc still renders cleanly so the bug is invisible at
  preview time, but RAG chunkers / link checkers / dead-link reports
  surface a "live" URL that is in fact unreferenced. Common artifact
  when an edit removed an inline reference but left the definition.
- **`duplicate_definition`** — two definitions with the same label
  and different URLs. CommonMark says the first wins; renderers vary
  (markdown-it honors first; some legacy parsers honor last). Almost
  always a model artifact where the generator emitted the same label
  from two different sources.
- **`empty_label`** — `[][]` or `[text][]` where the collapsed-
  reference label resolves to an empty string after normalization.
  Always a bug.
- **`label_case_mismatch`** — reference uses `[OAuth]` but only
  `[oauth]: ...` is defined. CommonMark label matching is
  case-insensitive AND whitespace-collapsing, so the link resolves
  correctly, but the case mismatch is a strong signal that the model
  lost its own naming convention mid-document. Soft-warning kind.

## Design notes

- **Fence-aware.** Fenced code blocks (` ``` ` / `~~~`) and inline
  `code` spans are stripped before scanning, so a code sample that
  legitimately mentions `[fake_ref]` does not false-positive.
  Replacement is same-length space runs so line numbers stay
  correct.
- **CommonMark-aligned label normalization.** Case-fold and collapse
  internal whitespace. `[Foo Bar]`, `[foo bar]`, `[FOO  BAR]` all
  resolve to the same definition. The `label_case_mismatch` kind
  detects pre-normalization differences so a project that enforces
  PascalCase labels can fail CI on drift.
- **Single-line references only.** Multi-line reference labels are
  legal in CommonMark but vanishingly rare in LLM output, and the
  false-positive cost of a stricter parser outweighed the recall
  gain.
- **Pure function over `str`.** No Markdown library, no networking,
  no URL validation (that's
  `llm-output-url-scheme-allowlist-validator`'s job).
- **Stable sort:** findings sorted by `(line_no, kind, label)` so
  byte-identical re-runs make diff-on-the-output a valid CI signal.

## API

```python
from validator import detect, format_report

findings = detect(markdown_text)
print(format_report(findings))
```

Each `Finding` carries `line_no`, `kind`, `label`, `detail`.

## Worked example

`example.py` exercises seven cases. Run it directly:

```
python3 example.py
```

Captured output (verbatim):

```
=== case 01 clean — every reference resolves, every definition is used ===
OK: no link-reference issues found.

=== case 02 undefined reference (truncated definitions block) ===
FOUND 1 link-reference issue(s):
  line 1 kind=undefined_reference label='runbook': full-reference with no matching definition

=== case 03 orphan definition (edit removed the prose, left the def) ===
FOUND 1 link-reference issue(s):
  line 4 kind=orphan_definition label='postmortem': definition -> https://example.org/postmortem is never referenced

=== case 04 duplicate definitions with conflicting URLs ===
FOUND 1 link-reference issue(s):
  line 3 kind=duplicate_definition label='spec': first defined line 3 -> https://example.org/spec-v1.html; later: line 4 -> https://example.org/spec-v2.html

=== case 05 empty label — collapsed reference with empty body ===
FOUND 1 link-reference issue(s):
  line 1 kind=empty_label label='': empty label in collapsed-reference

=== case 06 case mismatch — reference resolves but the casing drifted ===
FOUND 1 link-reference issue(s):
  line 1 kind=label_case_mismatch label='OAuth': reference [OAuth] resolves to definition [oauth] (line 3) via case-insensitive match

=== case 07 fence-aware: a [fake_ref] inside a code block must NOT flag ===
FOUND 1 link-reference issue(s):
  line 8 kind=undefined_reference label='missing_ref': full-reference with no matching definition
```

What the cases prove:

- **01** every reference resolves and every definition is used —
  silent pass, no false positives on healthy reference-style prose.
- **02** an undefined reference (the most common LLM artifact —
  generator truncated before the definitions block) is flagged with
  the exact label and line, so a repair prompt is one interpolation
  away.
- **03** an orphan definition is surfaced even though the doc still
  renders cleanly. Operators who run dead-link reports already see
  this; this gate catches it pre-publish.
- **04** two definitions for the same label with different URLs are
  flagged once on the first definition's line, with the conflicting
  later URL spelled out in the detail string — enough information
  for the reviewer to pick the correct URL without re-reading the
  document.
- **05** a `[][]` collapsed reference with empty label is flagged as
  its own kind. There is no way to define an empty-label target in
  CommonMark, so the only repair is to remove the reference or
  populate the label.
- **06** a casing drift from `[OAuth]` to `[oauth]: ...` resolves
  correctly under CommonMark but fires the soft `label_case_mismatch`
  kind so projects that enforce label casing can fail CI on drift,
  while projects that don't can suppress the kind.
- **07** the same reference text inside a fenced code block does NOT
  fire (the fence-strip ran first), but the matching reference
  outside the fence DOES fire — proves the fence-stripping
  preserves line numbers (the undefined reference correctly reports
  `line 8`).

## Composition

- **`llm-output-markdown-heading-level-skip-detector`** /
  **`llm-output-markdown-ordered-list-numbering-monotonicity-validator`**
  — orthogonal Markdown-structure gates with the same `Finding`
  shape and stable sort, so a single CI step can union them.
- **`llm-output-url-scheme-allowlist-validator`** — the natural
  follow-up: this gate confirms references resolve to *some*
  definition; that gate confirms the URL is acceptable. Run this
  gate first so the allowlist gate sees only the URLs the document
  actually uses.
- **`llm-output-zero-width-character-detector`** — a `U+200B` inside
  a label `[run​book]` would silently break the case-insensitive
  match. Run that gate before this one to keep label comparison
  honest.
- **`citation-id-broken-link-detector`** — sibling concept on a
  different artifact (citation IDs vs Markdown reference labels);
  same finding-shape pattern.
- **`agent-output-validation`** — feed `(kind, label)` into the
  repair prompt for a one-turn fix
  (`"add a definition for [API_DOCS] or remove the reference"`).
- **`structured-error-taxonomy`** —
  `do_not_retry / attribution=model` for `undefined_reference`,
  `orphan_definition`, `duplicate_definition`, `empty_label`
  (corrective-system-message fixes them; a plain retry will
  reproduce); `label_case_mismatch` is `info` and never fails CI.

## Tuning

- For projects that allow orphan definitions intentionally (a shared
  definitions block included from a partial), filter out
  `orphan_definition` at the caller.
- For projects that don't enforce label casing,
  `label_case_mismatch` can be silenced.
- The fence-strip is a defensive default; if your pipeline already
  runs `llm-output-fence-extractor` first you can pass the
  prose-only output and skip the redundant work.
