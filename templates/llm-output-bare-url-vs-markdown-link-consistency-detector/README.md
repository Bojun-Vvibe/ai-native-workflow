# llm-output-bare-url-vs-markdown-link-consistency-detector

Pure-stdlib detector for **mixed URL-citation styles** in LLM-generated
Markdown. Catches the case where the same document hands you bare
URLs, autolinks, and inline markdown links interleaved without any
style discipline.

## Why this exists

LLMs frequently mix three (or four) different ways of expressing the
same URL within one document because no single training-data
convention dominates:

| Form | Example |
|---|---|
| `bare_url` | `https://example.com/path` |
| `autolink` | `<https://example.com/path>` |
| `markdown_link` (inline) | `[example.com](https://example.com/path)` |
| `markdown_link` (reference) | `[example.com][ex]` … `[ex]: https://example.com/path` |

Each renders **differently** depending on the consumer:

- A strict CommonMark renderer with bare-URL detection disabled
  shows `bare_url` as plain text — not clickable.
- A plain-text export of `markdown_link` keeps the link text but loses
  the URL; an export of `bare_url` keeps the URL but has no link text.
- A documentation linter that requires every external reference to be
  a `markdown_link` (so that link text answers "what is this?") fails
  loudly on a bare URL but silently on an autolink — until someone
  reads the rendered output and notices the difference.

The bug is **mixed styles in one document**, not "the model used
bare URLs". A model that writes 30 bare URLs in a row is consistent
and easy to bulk-fix. A model that writes 28 inline links and 2 bare
URLs is the bug — those 2 bare URLs are easy to miss in review and
the diff against a corrected output is small enough to look like a
"meaningless style nit" that gets dismissed.

## Detected kinds

Each occurrence of a URL gets exactly one finding:

- `markdown_link` — `[text](url)` or reference form `[text][label]` +
  `[label]: url`. Reference-form findings carry `reference=True`.
- `autolink` — `<https://...>`.
- `bare_url` — anything else that matches `https?://...`.

URLs inside fenced code blocks (``` … ```) and inline code spans
(`` `…` ``) are reported with `in_code=True` and are **excluded from
the consistency verdict by default**. Code samples need bare URLs
(curl examples, log lines) and shouldn't drag the surrounding prose
into a `mixed_styles` verdict.

## Verdict

After classification, `evaluate_consistency` returns one of:

| Verdict | Meaning |
|---|---|
| `consistent` | All non-code URLs are the same kind. |
| `mixed_styles` | Two or more kinds appear outside code. The verdict names the dominant kind and lists the off-style occurrences so a one-shot repair prompt can target them by line. |
| `no_urls` | Nothing to evaluate. |

Tie-breaking when two kinds have the same count is fixed (preference
order: `markdown_link`, `autolink`, `bare_url`,
`markdown_reference_link`) so two runs against the same document
produce identical verdicts.

## Operator knobs

- `include_code=False` *(default)*: code URLs ignored for the verdict.
  Worked example case 04.
- `include_code=True`: strict mode; code URLs count. Worked example
  case 05 demonstrates the policy flip.
- `treat_reference_as_inline=True` *(default)*: reference-style links
  collapse into the `markdown_link` bucket. A document that uses
  `[text][label]` consistently is `consistent`.
- `treat_reference_as_inline=False`: reference style is its own
  bucket — useful for pipelines that mandate inline-only.

## API

```python
from detector import detect_url_styles, evaluate_consistency, format_report

findings = detect_url_styles(text)
verdict = evaluate_consistency(findings)
print(format_report(findings, verdict))
if verdict.verdict == "mixed_styles":
    # ask the model: "rewrite the URLs at lines [...] in markdown_link form"
    ...
```

Findings are sorted by `offset` so byte-identical re-runs make
diff-on-the-output a valid CI signal.

## Worked example

`example.py` exercises six cases. Run it directly:

```
python3 example.py
```

Captured output (verbatim):

```
=== 01 all inline markdown links ===
FINDINGS (2):
  line 1 offset 4: markdown_link https://example.com/spec
  line 1 offset 45: markdown_link https://example.com/rfc

VERDICT: consistent
  dominant_kind: markdown_link
  counts: markdown_link=2

=== 02 all bare urls ===
FINDINGS (3):
  line 1 offset 6: bare_url https://example.com/a
  line 1 offset 29: bare_url https://example.com/b
  line 1 offset 56: bare_url https://example.com/c

VERDICT: consistent
  dominant_kind: bare_url
  counts: bare_url=3

=== 03 mixed three styles in prose ===
FINDINGS (3):
  line 1 offset 12: markdown_link https://example.com/overview
  line 1 offset 62: bare_url https://example.org/mirror
  line 1 offset 98: autolink https://example.net/src

VERDICT: mixed_styles
  dominant_kind: markdown_link
  counts: autolink=1, bare_url=1, markdown_link=1
  off_style (2):
    line 1: bare_url https://example.org/mirror
    line 1: autolink https://example.net/src

=== 04 prose with bare url only inside fenced code (default policy) ===
FINDINGS (3):
  line 1 offset 5: markdown_link https://example.com/docs
  line 4 offset 62: bare_url https://example.com/raw [in_code]
  line 7 offset 101: markdown_link https://example.com/next

VERDICT: consistent
  dominant_kind: markdown_link
  counts: markdown_link=2

=== 05 same as 04 but include_code=True (strict) ===
FINDINGS (3):
  line 1 offset 5: markdown_link https://example.com/docs
  line 4 offset 62: bare_url https://example.com/raw [in_code]
  line 7 offset 101: markdown_link https://example.com/next

VERDICT: mixed_styles
  dominant_kind: markdown_link
  counts: bare_url=1, markdown_link=2
  off_style (1):
    line 4: bare_url https://example.com/raw

=== 06 reference-style markdown links collapse with inline by default ===
FINDINGS (4):
  line 1 offset 4: markdown_link https://example.com/spec [reference]
  line 1 offset 22: markdown_link https://example.com/rfc [reference]
  line 3 offset 42: markdown_link https://example.com/spec [reference]
  line 4 offset 72: markdown_link https://example.com/rfc [reference]

VERDICT: consistent
  dominant_kind: markdown_link
  counts: markdown_link=4

```

What the cases prove:

- **01** a document that exclusively uses inline markdown links is
  `consistent` with `dominant_kind=markdown_link` — no false positive
  for "bare URL inside the link target".
- **02** a document of pure bare URLs is *also* `consistent` — the
  detector's job is style **consistency**, not enforcing a particular
  style. Operators who want to ban bare URLs entirely should layer a
  separate "must be markdown_link" check after this detector.
- **03** the canonical bug: three URLs, three styles, one document.
  The verdict names `markdown_link` as dominant and lists the two
  off-style occurrences (the bare URL and the autolink) with their
  line numbers — exactly the input a one-shot repair prompt needs.
- **04** a `curl` URL inside a fenced code block does not break the
  consistency of the surrounding prose. The finding is still reported
  (with `[in_code]`) so the operator can see it; the verdict stays
  `consistent` because that's the right call for the prose layer.
- **05** flipping `include_code=True` on the *same* input flips the
  verdict to `mixed_styles` and surfaces the code URL as off-style.
  This is the strict-mode policy for documentation pipelines that
  also require code samples to use markdown links (for instance,
  generated tutorials where the renderer can't make plain text into
  a hyperlink). The toggle proves the knob is real, not decorative.
- **06** a document built entirely on reference-style markdown links
  (`[text][label]` plus `[label]: url`) is `consistent` under the
  default policy. The four findings are the two ref *definitions*
  plus the two ref *usages* — both are real source-level URL
  appearances and both must be reported so a downstream "all URLs use
  HTTPS" or "no URL appears in two definitions with conflicting
  targets" check sees the full set.

## Composition

- **`llm-output-link-reference-definition-orphan-detector`** — the
  catalog already covers orphaned `[label]: url` definitions. This
  detector is orthogonal: it answers "what *style* are the
  resolved-and-used links in?" while that one answers "are any
  reference labels dangling?". Run both — same `Finding` shape, same
  stable sort, single CI step can union the reports.
- **`llm-output-url-scheme-allowlist-validator`** — feed the URLs
  this detector finds into the scheme allowlist; the two together
  cover both *style* and *target* hygiene.
- **`llm-output-citation-bracket-balance-validator`** /
  **`llm-citation-anchor-resolution-validator`** — adjacent layers in
  the citation-hygiene family. Run after them: an unbalanced bracket
  can produce a phantom `[text](url)` match, so balance first, then
  classify style.
- **`structured-error-taxonomy`** — `mixed_styles` should classify
  as `do_not_retry / attribution=model`; the model emitted prose
  without a style instruction. The fix is a one-shot rewrite, not a
  retry.
- **`agent-output-validation`** — feed `verdict.off_style` into a
  repair prompt:
  `"rewrite each of these line numbers in markdown_link form: [...]"`.

## Tuning

- For prose / Markdown documentation pipelines, default settings.
- For pipelines that allow code samples to keep their bare URLs but
  enforce consistent prose, default settings (this is the common case).
- For "everything must be a clickable hyperlink" pipelines (generated
  HTML where the renderer cannot promote bare URLs), set
  `include_code=True`.
- For "no reference-style links" pipelines (some static-site
  generators), set `treat_reference_as_inline=False` and treat
  `markdown_reference_link` in `off_style` as a violation.
