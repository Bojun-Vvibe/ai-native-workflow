# prompt-drift-detector

Pure, structural drift detector for **a candidate prompt against a
pinned baseline prompt**. Returns a typed report naming *which class*
of structural change happened — sections added, removed, reordered,
or silently expanded/shrunk — so the caller can route on the cause,
not just on "the strings differ."

Stdlib-only. Pure: returns a new report, never mutates inputs.
Deterministic: same baseline + candidate always produce the same
report.

## Why structural, not textual

A diff that says "47 characters changed" is not actionable. The
interesting failure modes for production prompts are structural:

* A new section quietly appears (often a copy-paste from another
  mission's system prompt — including its safety stance).
* An existing section disappears (a templating bug that fails open).
* Sections get reordered (changes priority interpretation for some
  models, breaks a downstream extractor that anchors on section
  position).
* A section *silently grows* — the `# Tools` block balloons from 5
  bullets to 80 because someone forgot to scope a `for tool in
  tools` loop.

This detector flags each class with its own field on the report so
the caller can wire different policies per class — block on
removed-sections, log on reordered, page on a `# Safety` section
disappearing, etc.

## When to use

* You ship a long, multi-section system prompt and you've pinned a
  baseline you trust.
* Your prompt is assembled at runtime from multiple fragments
  (templating, runtime injection, per-tenant overrides) and you
  want a guardrail before the assembled result goes out.
* You want a fast, dependency-free signal in CI that flags "the
  system prompt's shape changed in this PR" without needing a
  reviewer to read the whole diff.

## When NOT to use

* You need *semantic* equivalence ("does this prompt still mean the
  same thing?"). That is a model-eval problem, not a structural
  one — pair this with `llm-eval-harness-minimal`.
* The prompt has no headers or other obvious structural delimiters.
  Drift on a 200-line prose block is too coarse to be useful here;
  use a fingerprint diff (`prompt-fingerprinting`) instead.
* You want to *block edits*. This is detection, not enforcement.
  The caller decides what to do with the report.

## Composes with

* `prompt-fingerprinting` — fingerprint hash answers "is this
  exactly the pinned baseline?"; this answers "if not, what shape
  of change happened?".
* `prompt-version-pinning-manifest` — the manifest names the
  baseline by hash; this detector explains *what changed* when the
  hash mismatches.
* `prompt-template-versioner` — version bumps from the templater
  feed both the manifest (which baseline to compare against) and
  this detector (run at template render time).

## Inputs / outputs

`detect_drift(baseline, candidate, *, header_re=DEFAULT_HEADER_RE,
abs_line_threshold=5, rel_line_threshold=0.5) -> DriftReport`

* `baseline: str` — the pinned reference prompt.
* `candidate: str` — the prompt about to be sent.
* `header_re: re.Pattern[str]` — regex matching section headers;
  group(1) must capture the header *name*. Defaults to
  ATX-style markdown (`^#{1,6}\\s+(\\S.*)$`). Pass your own pattern
  for non-markdown formats (`<!-- section: foo -->`, `[FOO]`, …).
* `abs_line_threshold: int` — absolute line-delta floor for
  flagging a section as `expanded_or_shrunk`. Default `5`.
* `rel_line_threshold: float` — relative line-delta floor (fraction
  of baseline section length). Default `0.5`. The detector flags
  when `abs(delta) > max(abs_line_threshold, baseline_lines *
  rel_line_threshold)` — the larger of the two thresholds wins, so
  small sections aren't flagged on tiny edits and large sections
  can't hide medium edits.

`DriftReport` fields: `is_drifted: bool`, `added_sections`,
`removed_sections`, `reordered_sections: bool`, `expanded_or_shrunk`
(tuple of `SectionDelta`), `baseline_section_order`,
`candidate_section_order`. Section names are lower-cased; renaming
a header is correctly modelled as `removed(old) + added(new)`.

## Worked example

`worked_example.py` runs three scenarios end-to-end against a
3-section baseline (`# Identity`, `# Tools`, `# Output format`).

* **Whitespace-only edit** — adds trailing space to one bullet.
  Report: `is_drifted=False`. The detector counts lines, not bytes,
  so this correctly does not fire.
* **Section added + reordered** — inserts a `# Safety` section at
  the top and swaps `# Tools` and `# Output format`. Report:
  `is_drifted=True`, `added_sections=['safety']`,
  `reordered_sections=True`, candidate order shows the swap.
* **Silent section expansion** — `# Tools` grows from 5 lines to
  16 lines (no name change, no order change). Report:
  `is_drifted=True`, `expanded_or_shrunk` flags `'tools'` with
  `delta=+11`. The threshold is `max(5, int(5 * 0.5)) = 5`, and
  `+11` exceeds it.

### Verbatim stdout

```
--- whitespace-only edit (no drift) ---
  is_drifted        : False
  added_sections    : []
  removed_sections  : []
  reordered_sections: False
  expanded/shrunk   : (none)
  baseline order    : ['identity', 'tools', 'output format']
  candidate order   : ['identity', 'tools', 'output format']

--- section added + reordered ---
  is_drifted        : True
  added_sections    : ['safety']
  removed_sections  : []
  reordered_sections: True
  expanded/shrunk   : (none)
  baseline order    : ['identity', 'tools', 'output format']
  candidate order   : ['safety', 'identity', 'output format', 'tools']

--- silent section expansion ---
  is_drifted        : True
  added_sections    : []
  removed_sections  : []
  reordered_sections: False
  expanded/shrunk   : 'tools': 5 -> 16 (delta=+11)
  baseline order    : ['identity', 'tools', 'output format']
  candidate order   : ['identity', 'tools', 'output format']
```

Reordering is detected even when no sections are added or removed —
the detector compares the order of the *common* section names
between baseline and candidate.
