# `llm-output-markdown-image-alt-text-presence-validator`

Pure stdlib gate for missing or non-informative alt text on inline
markdown images (`![alt](url)`). Catches the bug class where an LLM
emits an image but leaves the alt-text bracket empty, fills it with
a placeholder word, or copies the URL's filename in lieu of describing
the image. The rendered HTML still loads the image, but the document
is now hostile to screen readers, useless when the image 404s, and
fails any accessibility lint (axe-core, Pa11y, alt-text rules in
markdownlint plugins).

Three finding kinds:

- `empty_alt` — the bracket between `![` and `](` is empty or
  whitespace-only.
- `placeholder_alt` — alt text matches a curated lowercase placeholder
  list: `image`, `alt`, `picture`, `img`, `screenshot`, `todo`, `tbd`,
  `placeholder`, `figure`. These are the words an LLM types when it
  doesn't know what to put.
- `filename_as_alt` — alt text equals the URL's last path segment
  (case-insensitive), or strips to a bare image filename like
  `diagram.png`. Tells you the model copied the basename instead of
  describing the image content.

Reference-style images (`![alt][ref]`) and HTML `<img>` tags are
intentionally **out of scope** — reference-style images are caught by
the link-reference orphan detector; HTML `<img>` is a separate parser
concern (raw HTML mixed into markdown).

## When to use

- Pre-publish gate on any LLM-generated **README / docs page /
  changelog** that will be rendered on a site with an accessibility
  budget (the rule of thumb is "every image needs alt text, full
  stop"; this template enforces the negative half).
- Pre-commit guardrail on LLM-drafted **architecture writeups** —
  diagrams without alt text become invisible the moment the asset
  bucket migrates and the URL breaks.
- Audit step in a **review-loop** that promotes
  [`agent-output-validation`](../agent-output-validation/)'s
  `repair_once` policy: a finding's `line`, `column`, and `kind` feed
  back into the repair prompt as "describe the image at this URL in
  one sentence".
- Cron-friendly: findings are sorted by `(line, column, kind)`, so
  byte-identical output across runs makes diff-on-the-output a valid
  CI signal.

## Inputs / outputs

```
validate_image_alt_text(text: str) -> list[Finding]

Finding(kind: str, line: int, column: int, raw: str, detail: str)
```

- `text` — the LLM markdown output to scan. Must be `str` (raises
  `ValidationError` otherwise). `line` / `column` are 1-indexed and
  point at the leading `!` of the offending image.
- Returns the list of findings sorted by `(line, column, kind)`.
- `format_report(findings)` renders a deterministic plain-text report.

Pure function: no I/O, no markdown parser dependency, no network, no
vision model. Fenced code blocks (``` and `~~~`) are skipped so an
image-shaped line inside a literal-markdown example never trips the
gate. `_PLACEHOLDERS` is a frozen set; extend it by subclassing or by
patching the module attribute in the caller's test fixture.

## Composition

- [`agent-output-validation`](../agent-output-validation/) — feed a
  finding's `kind` and `line` into the repair prompt for a one-turn
  fix; the repair prompt should include the URL so the model can
  fetch + describe the image (or refuse and surface a TODO).
- [`structured-output-repair-loop`](../structured-output-repair-loop/) —
  the per-attempt validator inside the loop's `validate(attempt)`
  callback; identical-fingerprint repeat findings (same `kind` + same
  `line`) make a stuck loop trivially detectable (the model keeps
  re-emitting `![image](...)`).
- [`llm-output-markdown-bullet-marker-consistency-validator`](../llm-output-markdown-bullet-marker-consistency-validator/) —
  orthogonal: same `Finding` shape and stable sort, so a single CI
  step can union both detectors' findings.
- [`structured-error-taxonomy`](../structured-error-taxonomy/) —
  classifies `empty_alt` and `placeholder_alt` as
  `repair_once / attribution=model`; `filename_as_alt` is
  `repair_once / attribution=model` plus a hint that the model needs
  the image content, not just the URL.

## Worked example

```
$ python3 example.py
```

Verbatim output:

```
=== 01-clean-informative-alt ===
OK: every image has informative alt text.

=== 02-empty-alt ===
FOUND 1 image-alt finding(s):
  [empty_alt] line=3 col=1 raw='' :: url='https://example.invalid/arch.png'

=== 03-placeholder-alt ===
FOUND 2 image-alt finding(s):
  [placeholder_alt] line=3 col=1 raw='image' :: placeholder='image'; url='https://example.invalid/one.png'
  [placeholder_alt] line=7 col=1 raw='Screenshot' :: placeholder='screenshot'; url='https://example.invalid/two.png'

=== 04-filename-as-alt ===
FOUND 1 image-alt finding(s):
  [filename_as_alt] line=1 col=12 raw='diagram.png' :: alt equals url basename='diagram.png'

=== 05-fenced-code-is-ignored ===
OK: every image has informative alt text.

=== 06-multiple-images-one-line ===
FOUND 2 image-alt finding(s):
  [empty_alt] line=1 col=9 raw='' :: url='https://example.invalid/a.png'
  [placeholder_alt] line=1 col=51 raw='image' :: placeholder='image'; url='https://example.invalid/b.png'

```

Notes:

- Case 03 is case-insensitive on the placeholder match: `Screenshot`
  → `screenshot` → hit. The reported `raw` preserves original casing
  so the auto-fixer can match the source text byte-for-byte.
- Case 04's first image trips `filename_as_alt` because the alt text
  is *exactly* the URL basename. The second image (`alt='chart'`,
  basename `chart.png`) deliberately does **not** trip — `chart` is
  a (terse) word, not a filename, and the validator is a presence
  gate, not a length linter.
- Case 05 demonstrates fence-skipping: an `![](...)` line inside a
  ``` block is literal example markup, not a real image, so the
  surrounding clean image with informative alt passes.
- Case 06 shows multiple images on the same line: each one is
  independently classified, with `column` pinpointing the leading
  `!` of each. The third image (informative alt) does not appear in
  the report — only the two offenders do.

## Files

- `validator.py` — pure stdlib detector + `format_report`
- `example.py` — six-case worked example
