# `llm-output-hyperlink-empty-text-detector`

Pure-stdlib detector for **Markdown inline hyperlinks with
empty or whitespace-only link text**:

```
[](https://example.com)
[   ](https://example.com)
[\u00a0](https://example.com)   # NBSP-only
```

These render as zero-width clickable regions in GitHub, GitLab,
and most static-site generators. The link is live, billable,
and SEO-indexed — but **invisible to humans and screen
readers**. LLMs produce this when they "remember" they should
cite a source mid-sentence, lose the anchor text, and emit the
URL anyway.

Three finding kinds:

- `empty_text`           — `[]` (literally nothing).
- `whitespace_only_text` — only ASCII space/tab between brackets.
- `invisible_only_text`  — only non-ASCII whitespace (NBSP `\u00a0`,
  ZWSP `\u200b`, ideographic space `\u3000`, …). Reported
  separately because the failure mode is different: the model
  *thought* it produced anchor text and emitted invisible
  bytes, which calls for a different repair prompt than "you
  forgot to write anything".

Fenced code blocks (` ``` ` and `~~~`) are skipped wholesale,
so docs that demonstrate the bad pattern do not self-trigger.

Reference-style links (`[text][ref]`, `[ref]: url`) are out of
scope; the orphan-reference variant lives in
`llm-output-link-reference-definition-orphan-detector`.

## When to use

- Pre-publish gate on any LLM-authored **PR description**,
  **release note**, **runbook**, or **doc-site page** before
  it is merged to a default branch. An empty-text link is a
  silent accessibility regression and a silent attribution
  failure at the same time.
- Inside a **review-loop validator**: each finding's
  `(line_number, column, url)` triple is small and stable, so
  the same finding twice in a row across repair attempts is a
  reliable "give up and escalate" signal.
- As a **citation-pipeline postcondition** when a prompt asks
  the model to cite N sources inline. An empty-text link means
  the URL survived but the anchor evaporated — the citation is
  technically present but practically lost.

## Usage

```
python3 detector.py [FILE ...]   # FILEs, or stdin if none
```

Exit code: `0` clean, `1` at least one finding. JSON to stdout.
Pure stdlib; no third-party deps.

## Composition

- `agent-output-validation` — feed `findings` into a repair
  prompt verbatim; each entry's `url` is enough context for
  the model to regenerate a correct anchor.
- `llm-output-link-reference-definition-orphan-detector` —
  orthogonal: that template covers reference-style links with
  missing definitions, this one covers inline links with
  missing text.
- `llm-output-bare-url-vs-markdown-link-consistency-detector` —
  if your house style requires bare URLs in some sections and
  Markdown links in others, run both: bare-url detector
  enforces *which form*, this detector enforces *that the form
  has anchor text*.

## Worked example

Input is `worked-example/input.md` — planted issues for all
three kinds plus negative cases (real link, auto-link,
reference link, fenced examples).

```
$ python3 detector.py worked-example/input.md
```

Verbatim output is captured in
`worked-example/expected-output.txt` (exit code `1`, 6
findings):

- line 5  — `empty_text`           — `[](.../paper-1)`
- line 7  — `whitespace_only_text` — three ASCII spaces
- line 9  — `invisible_only_text`  — single NBSP
- line 32 — `empty_text`           — appears after a fenced block
- line 34 — `empty_text`           — first of two on one line
- line 34 — `whitespace_only_text` — second of two on one line

Notes on what is **NOT** flagged (intentionally):

- `<https://example.com/auto>` — auto-links have no text slot.
- `[link][ref]` plus `[ref]: …` — reference style is out of
  scope.
- The two empty-text links *inside* the ` ``` ` and `~~~`
  fenced blocks at lines 23–25 and 29–31 — fences are skipped
  wholesale.
- `[text]()` — empty URL, not a finding (the URL must be
  non-empty for the regex to match; an empty URL is a
  different problem and belongs in a URL-validity detector).

## Files

- `detector.py` — pure-stdlib detector + JSON renderer + CLI
- `worked-example/input.md` — planted-issue input (real NBSP)
- `worked-example/expected-output.txt` — captured exit + JSON
- `README.md` — this file

## Limitations

- Only inline links of the form `[text](url)` are inspected.
  Reference, auto, and HTML `<a>` links are out of scope.
- The detector does not validate the URL itself. A nonsense
  scheme, a 404, or an internal-only hostname is fine here;
  see `llm-output-url-scheme-allowlist-validator` for that.
- Empty *image* alt text (`![](img.png)`) is a separate
  accessibility concern handled by
  `llm-output-markdown-image-alt-text-presence-validator`.
- Nested brackets in link text (`[[x]](url)`) are not parsed
  — the regex is conservative and skips brackets inside
  brackets to stay linear-time and avoid pathological inputs.
