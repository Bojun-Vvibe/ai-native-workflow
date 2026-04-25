# llm-citation-anchor-resolution-validator

Pure stdlib detector for structural failures in the citation layer of LLM
output: inline `[N]`-style anchors in prose paired with an attached
ordered list of citation entries. Catches the four classes of bug that
silently corrupt downstream "open the linked source" / "extract the
citation list to a footnotes section" behaviour — the rendered article
looks fine but a reader who clicks the anchor lands nowhere.

## Why a separate template

Existing prompt-side templates (`prompt-template-variable-validator`,
`prompt-section-order-canonicalizer`) check the *prompt*. Existing
output-side templates (`agent-output-validation`,
`structured-output-repair-loop`) validate JSON shape. **Neither catches
"the model emitted `[3]` in prose but never produced citation #3"** —
the JSON is well-formed, the schema passes, the prose reads naturally,
the bibliography just doesn't line up. This template plugs that gap.

## Findings

Deterministic order: `(kind, anchor_id)` — two runs over the same input
produce byte-identical output (cron-friendly diffing).

| kind | severity | what it catches |
|---|---|---|
| `unresolved_anchor` | hard | prose says `[N]` but no citation #N is provided |
| `duplicate_id` | hard | two citation entries claim the same id N |
| `unused_citation` | warn | citation #N provided but never referenced — disable via `flag_unused=False` for drafts that legitimately ship a wider bibliography |
| `non_contiguous` | warn | citation ids skip numbers (1,2,4) — usually a deleted entry whose anchor was left behind |
| `empty_target` | hard | citation #N exists but both `url` and `text` are empty/whitespace |
| `malformed_id` | hard | non-positive-integer id, or `[0]` / `[-1]` / `[1.0]` in prose |

`ok` is `False` iff any **hard** finding fires. `unused_citation` and
`non_contiguous` are warnings — caller decides via `report.kinds()`
whether to treat them as failures.

## Design choices

- **Eager refusal on bad input.** `prose` not a string or `citations`
  not a list raises `CitationValidationError` immediately. The rest of
  the analysis would be ambiguous and a silent empty-findings report
  would be worse than a stack trace.
- **`unused_citation` is a warning, not a hard fail.** Many drafts
  legitimately ship a wider bibliography than they cite (related-work
  sections, "for further reading"). Caller sets the policy.
- **`require_contiguous=True` by default but warn-only.** A gap (1,2,4)
  is the single best signal that the model deleted a citation entry but
  forgot to reflow the anchors. Cheap to detect, valuable to surface.
- **Pure function.** No I/O, no clocks, no transport. Composes anywhere.
- **Stdlib only.** `re`, `dataclasses`, `json` — nothing to install.

## Composition

- `agent-output-validation` validates the JSON envelope shape (does it
  have a `prose` field and a `citations` field at all?). This template
  validates the *contents* line up.
- `structured-output-repair-loop` can take an `unresolved_anchor`
  finding and feed it back as a one-shot repair hint ("you wrote `[3]`
  but only provided citations 1 and 2 — either remove the anchor or
  add citation #3").
- `agent-decision-log-format` — emit one log line per finding sharing
  `anchor_id` for queryable audit.
- `structured-error-taxonomy` — `unresolved_anchor` and `duplicate_id`
  classify as `attribution=tool` (model bug); `empty_target` classifies
  as `attribution=user` (the source-fetcher upstream returned an empty
  page).

## Run

```bash
python3 templates/llm-citation-anchor-resolution-validator/example.py
```

Pure stdlib. No `pip install`. Five worked cases — clean,
unresolved+unused, duplicate+empty_target, non-contiguous+malformed,
malformed citation id.

## Example output:

```
--- 01 clean ---
{
  "ok": true,
  "referenced_ids": [
    1,
    2
  ],
  "provided_ids": [
    1,
    2
  ],
  "findings": []
}

--- 02 unresolved + unused ---
{
  "ok": false,
  "referenced_ids": [
    1,
    3
  ],
  "provided_ids": [
    1,
    2
  ],
  "findings": [
    {
      "kind": "unresolved_anchor",
      "anchor_id": 3,
      "detail": "prose references [3] but no citation #3 is provided"
    },
    {
      "kind": "unused_citation",
      "anchor_id": 2,
      "detail": "citation #2 provided but never referenced in prose"
    }
  ]
}

--- 03 duplicate + empty_target ---
{
  "ok": false,
  "referenced_ids": [
    1,
    2
  ],
  "provided_ids": [
    1,
    2
  ],
  "findings": [
    {
      "kind": "duplicate_id",
      "anchor_id": 2,
      "detail": "citation id 2 provided 2 times"
    },
    {
      "kind": "empty_target",
      "anchor_id": 2,
      "detail": "citation #2 has empty url and text"
    }
  ]
}

--- 04 non-contiguous + malformed ---
{
  "ok": false,
  "referenced_ids": [
    1,
    2,
    4
  ],
  "provided_ids": [
    1,
    2,
    4
  ],
  "findings": [
    {
      "kind": "malformed_id",
      "anchor_id": null,
      "detail": "anchor [0] in prose is not a positive integer"
    },
    {
      "kind": "non_contiguous",
      "anchor_id": 3,
      "detail": "citation id 3 missing from provided ids (1..4)"
    }
  ]
}

--- 05 malformed citation id ---
{
  "ok": false,
  "referenced_ids": [],
  "provided_ids": [
    1
  ],
  "findings": [
    {
      "kind": "malformed_id",
      "anchor_id": null,
      "detail": "anchor [0] in prose is not a positive integer"
    },
    {
      "kind": "malformed_id",
      "anchor_id": null,
      "detail": "citations[0].id=0 is not a positive integer"
    },
    {
      "kind": "unused_citation",
      "anchor_id": 1,
      "detail": "citation #1 provided but never referenced in prose"
    }
  ]
}

=== summary ===
case 01: ok=True kinds=[]
case 02: ok=False kinds=['unresolved_anchor', 'unused_citation']
case 03: ok=False kinds=['duplicate_id', 'empty_target']
case 04: ok=False kinds=['malformed_id', 'non_contiguous']
case 05: ok=False kinds=['malformed_id', 'unused_citation']
```

The output proves the four invariants:
- **Case 01**: every prose anchor resolves and every citation is used → `ok=True`, no findings.
- **Case 02**: the missing `[3]` and the unused `#2` are surfaced separately so a caller can fix one without ignoring the other.
- **Case 03**: the same id `2` triggers both `duplicate_id` (structure) and `empty_target` (content) — two independent findings, both attached to anchor `2`.
- **Case 04**: a gap in the bibliography (1,2,4) is flagged at exactly the missing id `3`, and the `[0]` malformed anchor in prose is reported once even though the regex matched it.
- **Case 05**: a malformed citation id (`id=0`) is rejected and the dangling `[0]` in prose is also rejected — two independent `malformed_id` findings (anchor side + citations side) sorted together but with distinct `detail` text.
