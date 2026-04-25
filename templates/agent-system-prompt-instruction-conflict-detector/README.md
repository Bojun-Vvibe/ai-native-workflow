# agent-system-prompt-instruction-conflict-detector

Pure stdlib detector for *internal* contradictions in an agent's
system prompt — the failure mode where the prompt accumulates over
months of "just one more rule" edits until it contains, somewhere,
both:

> Always cite the source URL for every factual claim.
> Never cite URLs in your response because they break our renderer.

The model picks one of the two at random per call (sometimes
per-paragraph), and the team spends two weeks blaming "model drift"
before someone re-reads the prompt.

Three conflict classes:

- **`polarity_conflict`** (high severity) — one clause says
  ALWAYS X, another says NEVER X, and the two share at least 2
  content tokens after stopword + naive-plural normalization.
- **`quantifier_conflict`** (medium severity) — one clause is
  absolute (`always` / `must` / `never`), another is conditional
  (`sometimes` / `when appropriate` / `if needed`) about the same
  predicate. Lower-severity because the conditional clause may be
  intended as a refinement; the detector flags it and lets the caller
  decide.
- **`format_conflict`** (high severity) — two clauses prescribe
  *different specific values* for the same surface (`format`,
  `tone`, `length`, `language`, `list_style`). Detected against an
  extensible enum, not a free-text overlap, so "respond in markdown"
  vs "respond in plain text" is unambiguous.

## When to use

- Pre-merge gate on any system-prompt edit — fail the prompt PR if
  the new revision introduces a `polarity_conflict` or
  `format_conflict`. Catches the regression at review time, not after
  a week of degraded responses.
- CI assertion against a long-lived `system.txt` — periodic run
  surfaces accumulated drift from edits that individually looked
  fine.
- Forensic pass on a prompt that "the model keeps disobeying" — if
  the detector finds a conflict, the model isn't disobeying; it's
  picking one of two instructions you gave it.

## When NOT to use

- This is **not** an LLM judge. It is a deliberately structural
  lexical detector: same answer at 03:00 as at 15:00, runs in 50 ms
  in CI. The trade-off is that "always cite sources" vs "never use
  citations" needs the synonymy to be picked up by the caller — by
  default we only do naive plural normalization, not WordNet.
- This is **not** a semantic-correctness checker. It does not know
  whether your rules are *good* — only whether two rules in the
  prompt contradict each other.
- Conditional clauses that genuinely refine — e.g., "Always show
  working" + "Sometimes show working when the answer is obvious" —
  fire `quantifier_conflict` at medium severity. That's a feature: a
  human should look. Bypass with `min_overlap` tuning if your prompt
  domain genuinely needs both clauses.

## Design choices worth knowing

- **Polarity markers are matched longest-first.** "do not" matches
  before "do", "must not" before "must", so a negated imperative is
  never miscategorized as a positive one.
- **Naive plural normalization (not real stemming).** "urls" → "url",
  "claims" → "claim", "boxes" → "box"; words ending in "ss" are
  preserved (so "class", "address" are intact). Cheap, deterministic,
  and good enough for the overlap test. A real stemmer (Porter,
  Snowball) would be a drop-in upgrade but adds a dependency.
- **`min_overlap=2` default.** A single shared content token is too
  weak (e.g., "always cite sources" vs "never cite headers" share
  only "cite"). Two-token overlap is the empirical sweet spot for
  imperative-clause similarity in agent system prompts.
- **Findings are sorted `(kind, clause_a_line, clause_b_line)`.** Two
  runs over the same input produce byte-identical output; cron diffs
  don't churn.
- **Format conflicts use a closed enum, not free overlap.** The whole
  *point* of `format_conflict` is that the values are mutually
  exclusive members of a known set; trying to detect them from
  free-token overlap would conflate them with `polarity_conflict`.

## Composes with

- **`prompt-drift-detector`** — detects *which sections* of a prompt
  changed across revisions; this detector tells you whether the *new*
  prompt is internally consistent. Pair both in a prompt-PR check.
- **`prompt-version-pinning-manifest`** — once a prompt revision
  passes both drift and conflict detection, lock it.
- **`agent-decision-log-format`** — one log line per `Finding` with
  `kind`, `severity`, and the two offending line numbers.
- **`structured-error-taxonomy`** — every finding maps to
  `attribution=user` (the prompt author wrote contradictory rules)
  and `retryability=do_not_retry` (the prompt itself is the bug).

## Adapt this section

- `_FORMAT_TARGETS` — extend with domain-specific surfaces, e.g.,
  `("citation_style", ("apa", "mla", "chicago", "bluebook"))` for a
  legal-research agent.
- `_POS_MARKERS` / `_NEG_MARKERS` — add domain-specific imperatives,
  e.g., "you are required to" / "you are forbidden from".
- `min_overlap` — drop to 1 if your prompt domain has a small,
  high-signal vocabulary (rare); raise to 3 if your prompt is so long
  that 2-token overlap fires false positives.

## Worked example

`examples/example.py` runs four synthetic system prompts — one clean
control plus one per conflict class — and prints one JSON report per
prompt followed by a prompt-set tally.

Run from the repo root:

```
python3 templates/agent-system-prompt-instruction-conflict-detector/examples/example.py
```

### Worked example output

```
========================================================================
01 healthy
========================================================================
{
  "clause_count": 4,
  "finding_kind_totals": {},
  "findings": [],
  "ok": true
}

========================================================================
02 polarity_conflict
========================================================================
{
  "clause_count": 4,
  "finding_kind_totals": {
    "polarity_conflict": 1
  },
  "findings": [
    {
      "clause_a_line": 2,
      "clause_a_text": "Always cite the source URL for every factual claim",
      "clause_b_line": 4,
      "clause_b_text": "Never cite URLs in your response because they break our renderer",
      "detail": "clauses share 2 content tokens (['cite', 'url']) but opposite polarities",
      "kind": "polarity_conflict",
      "severity": "high"
    }
  ],
  "ok": false
}

========================================================================
03 quantifier_conflict
========================================================================
{
  "clause_count": 4,
  "finding_kind_totals": {
    "quantifier_conflict": 1
  },
  "findings": [
    {
      "clause_a_line": 2,
      "clause_a_text": "Always show your working step by step before giving the final answer",
      "clause_b_line": 3,
      "clause_b_text": "Sometimes show your working when the student is stuck",
      "detail": "clauses share 2 content tokens (['show', 'working']) but mix absolute and conditional quantifiers",
      "kind": "quantifier_conflict",
      "severity": "medium"
    }
  ],
  "ok": false
}

========================================================================
04 format_conflict
========================================================================
{
  "clause_count": 5,
  "finding_kind_totals": {
    "format_conflict": 2
  },
  "findings": [
    {
      "clause_a_line": 2,
      "clause_a_text": "Respond in markdown for clarity",
      "clause_b_line": 4,
      "clause_b_text": "For our voice channel, respond in plain text only",
      "detail": "target='format' prescribed both 'markdown' and 'plain text'",
      "kind": "format_conflict",
      "severity": "high"
    },
    {
      "clause_a_line": 3,
      "clause_a_text": "Use bullet lists when enumerating options",
      "clause_b_line": 5,
      "clause_b_text": "Use numbered lists so customers can refer to items by number",
      "detail": "target='list_style' prescribed both 'bullet' and 'numbered'",
      "kind": "format_conflict",
      "severity": "high"
    }
  ],
  "ok": false
}

========================================================================
summary
========================================================================
{
  "finding_kind_totals_across_prompts": {
    "format_conflict": 2,
    "polarity_conflict": 1,
    "quantifier_conflict": 1
  }
}
```

Notice case 02: the words `URL` and `URLs` share `url` after naive
plural normalization, so the detector correctly flags the
polarity_conflict on a 2-token overlap (`cite`, `url`) even though
the surface forms differ. Without the normalization the "same
predicate, opposite polarity" case would slip through any time the
prompt author varied the singular/plural for stylistic reasons —
which is exactly when a long prompt accumulates the bug.

Notice case 04: `format_conflict` fires *twice* on the same prompt,
on two different prescription targets (`format` and `list_style`).
This is intentional — a single prompt can carry independent
contradictions on multiple surfaces, and surfacing each one with its
target name tells the prompt author which lines to merge or remove.
