# `llm-output-markdown-link-reference-definition-duplicate-label-detector`

Pure stdlib gate for **duplicate link reference definitions** in
LLM-generated markdown. CommonMark says the *first* definition of a
given label wins and silently drops the rest; some legacy renderers
take the *last* one. Either way, the document silently picks one URL
and the author has no way to know which.

The classic LLM failure path:

1. Model writes a long article that ends with a footer block of
   `[label]: url` reference definitions.
2. A regenerate-pass rewrites a paragraph in the middle and emits a
   new `[api]: https://example.invalid/api/v2` while the original
   `[api]: https://example.invalid/api/v1` is still in the footer.
3. Both definitions ship. The renderer picks one. Half your readers
   land on v1, half on v2, and nobody notices until a support ticket.

This detector flags **every duplicate after the first** for each
case-folded label. It distinguishes three failure shapes:

- `duplicate_label` — same label, identical URL and title.
  Just a redundant copy. Lowest severity.
- `duplicate_label_conflicting_url` — same label, **different URL**
  from the winning definition. Highest severity: silent divergence
  depending on renderer choice.
- `duplicate_label_conflicting_title` — same label and URL but the
  optional title (`"..."`, `'...'`, `(...)`) differs. Hover-text
  drift; medium severity.

Label comparison uses CommonMark's normalization: case-fold, collapse
internal whitespace runs to a single space, trim. So `[The   Docs]`
and `[the docs]` and `[THE DOCS]` all collide.

The detector is **fence-aware**:

- Reference definitions inside ```` ``` ```` and `~~~` fenced code
  blocks are ignored.
- Indented code blocks (lines starting with 4 spaces or a tab) are
  ignored heuristically (CommonMark allows at most 3 leading spaces
  on a real reference definition).

## Out of scope

- Inline links `[text](url)` — they have no labels and cannot collide.
- Footnote definitions `[^id]: ...` — handled by the footnote-orphan
  detector elsewhere in this family.
- Reference *uses* with no matching definition — handled by
  `reference-link-undefined-label-detector`.

## When to use

- Pre-publish gate on any LLM-generated long-form document
  (blog post, RFC, README) that uses reference-style links in a
  footer block. The longer the doc, the higher the chance a
  regenerate pass duplicated a label.
- Pre-commit guardrail on LLM-drafted docs site pages — silent URL
  divergence is exactly the bug class that survives human review.
- Regression check after running an LLM-based markdown rewriter or
  link-canonicalizer over an existing corpus.

## Files

- `detector.py` — the detector. Single function
  `detect_duplicate_reference_definitions(text: str) -> list[Finding]`.
  Stdlib-only. Also runnable as a script:
  `python3 detector.py path/to/file.md`.
- `example.py` — eight worked cases (one clean + seven failing
  shapes). Run `python3 example.py` to see the detector in action.

## Verified output

Running the example reports **0 findings** on the clean case
(`01-clean-no-duplicates`), **0 findings** on the two
fence/indented-code cases (proving fence-awareness), and **8 total
findings** across cases 02, 03, 04, 05, and 08 covering all three
finding kinds.

## Exit code

`detector.py` exits `0` if no findings, `1` if any findings. Wire
it into a pre-commit / CI step to fail the build on duplicates.

## Wiring into a pipeline

```bash
# fail the commit if any tracked .md has duplicate reference defs
git ls-files '*.md' | while read -r f; do
  python3 path/to/detector.py "$f" || exit 1
done
```
