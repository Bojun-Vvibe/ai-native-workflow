# prompt-section-order-canonicalizer

Pure stdlib canonicalizer that reorders the **section order** of a system
prompt to a stable, declared ordering before cache-key derivation runs. Two
prompts that differ only in section order canonicalize to the same byte
string, so the prompt-cache key is stable across author reorderings.

## Problem

Two prompts that the model treats identically:

```
# Identity              # Identity
# Tools                 # Safety
# Output format    vs   # Output format
# Safety                # Tools
```

…produce different SHA-256 hashes and therefore different prompt-cache keys.
A "harmless" refactor that moves Safety up after Identity blows the cache for
every downstream call. The diff looks like a no-op in code review, the cost
spike shows up in the next billing cycle, and nobody notices the connection
because the cache miss is invisible at the call site.

This template runs *before* `prompt-cache-key-canonicalizer` (which handles
whitespace / smart-quote normalization). Together: section reordering
collapses, then byte-level normalization collapses, then the hash is taken.

## When to use

- Anywhere prompt-cache-key derivation is on the critical path (Anthropic
  prompt caching, vLLM prefix cache, your own context-cache layer).
- Long-lived agent system prompts maintained by multiple authors.
- CI gate: refuse a PR that re-orders sections without bumping the
  `prompt_version` if the canonical bytes do change (the gate runs the
  canonicalizer on both the old and new file and compares — a section ADD
  changes canonical bytes, a section REORDER does not).

## Design

- **Section identity** is the lower-cased trimmed header text. `# Identity`,
  `# IDENTITY`, and `## identity` all map to the key `identity`.
- **`canonical_order`** is a closed list of expected section keys in the
  desired output order. Required, non-empty, no duplicates, may not contain
  the reserved `__preamble__` key.
- **Pre-header content** becomes a synthetic `__preamble__` section that
  stays at the top regardless of order — re-anchoring a "system role +
  context" preamble would surprise authors and break a common pattern.
- **`unknown_policy`** governs sections present in the input but absent from
  `canonical_order`:

  | policy | behavior | when to use |
  |---|---|---|
  | `tail` (default) | append unknowns in original order *after* canonical sections | tolerant; new sections don't crash the pipeline |
  | `raise` | raise `PromptOrderError` | strict: "this prompt template is exhaustively declared" |
  | `drop` | silently drop unknowns; record in `dropped_keys` | sanitize a stale prompt; rarely the right answer |

- **Duplicate sections raise** `PromptOrderError`. Two `# Tools` blocks in
  one prompt is almost always an authoring bug; silent merge would change
  semantics.
- **Trailing whitespace within sections is preserved verbatim.** The only
  byte-level changes the canonicalizer makes are: (a) section blocks moved
  as units, (b) exactly one blank line between adjacent sections.
- **Idempotent**: `canonicalize(canonicalize(x, order), order).text ==
  canonicalize(x, order).text` (asserted in the worked example).
- **`moves` log**: every section that actually moved is recorded with its
  `from_index` and `to_index` (positions among non-preamble sections), so a
  CI gate can show "Tools moved from position 3 to position 1" — the diff is
  auditable, not just a hash change.
- **Configurable `header_re`** for non-markdown formats (`<!-- section: foo
  -->`, `[FOO]`, etc). Default matches ATX markdown `^#{1,6}\s+(\S.*?)$`.

## Files

- `canonicalizer.py` — `Section`, `Move`, `CanonicalizeResult`,
  `PromptOrderError`, `canonicalize()`. Stdlib only (`re`, `dataclasses`).
- `example.py` — five scenarios: same content + different order produces same
  canonical bytes; idempotency; unknown section under `tail` (default);
  unknown under `raise`; duplicate section in input.

## Worked example output

Captured by running `python3 templates/prompt-section-order-canonicalizer/example.py`:

```

=== Scenario 1: same content, different order -> same canonical bytes ===
  raw bytes equal? False
  raw sha A: f3ab1e3b4bab
  raw sha B: cd12fe30351d
  canonical sha A: f3ab1e3b4bab
  canonical sha B: f3ab1e3b4bab
  canonical bytes equal? True
  A summary: sections=4 moved=0 unknown=0 dropped=0 policy=tail
  B summary: sections=4 moved=2 unknown=0 dropped=0 policy=tail
  A moves: []
  B moves: [('tools', 3, 1), ('safety', 1, 3)]

--- canonical text (A and B both produce this) ---
You are a helpful agent.

# Identity
Name: aria
Role: code reviewer

# Tools
- read_file
- run_tests

# Output format
JSON with keys: verdict, comments

# Safety
Refuse offensive requests.

--- end ---

=== Scenario 2: idempotency -- canonicalize(canonicalize(x)) == canonicalize(x) ===
  once.text == twice.text? True
  twice.summary: sections=4 moved=0 unknown=0 dropped=0 policy=tail
  twice.moves: ()

=== Scenario 3: unknown section -> appended at tail (default) ===
  unknown_keys: ('examples',)
  summary: sections=3 moved=2 unknown=1 dropped=0 policy=tail
  section keys (canonical order): ['identity', 'tools', 'examples']

--- output ---
# Identity
You are aria.

# Tools
- read_file

# Examples
- Example 1
- Example 2

--- end ---

=== Scenario 4: unknown section under unknown_policy='raise' -> PromptOrderError ===
  raised PromptOrderError: unknown sections in input not in canonical_order: ['examples']

=== Scenario 5: duplicate section in input -> PromptOrderError ===
  raised PromptOrderError: duplicate section in input: 'tools'

=== all 5 scenarios asserted ===
```

Note in Scenario 1: prompt B's raw sha (`cd12fe30351d`) differs from A's
(`f3ab1e3b4bab`), so a cache key derived from the raw text would miss. The
canonicalized sha (`f3ab1e3b4bab`) is identical for both, and the move log
records exactly what was reordered (`tools 3->1`, `safety 1->3`).

## Composes with

- `prompt-cache-key-canonicalizer` — runs *after* this. Section reorder
  collapses first, then whitespace / smart-quote normalize, then SHA. Both
  steps must run for the cache key to be reorder- and edit-stable.
- `prompt-fingerprinting` — fingerprint the canonicalized text, not the raw
  text, so the fingerprint is stable across reorderings.
- `prompt-version-pinning-manifest` — the manifest's `prompt_sha` should be
  the canonical sha. A PR that re-orders sections does not bump the manifest
  version (canonical sha unchanged); a PR that adds, removes, or edits
  section content does.
- `prompt-drift-detector` — drift detector classifies *what changed* (added,
  removed, reordered, expanded). This canonicalizer ensures that a pure
  reorder doesn't downstream-trigger a cache miss the drift detector
  wouldn't even flag as a structural change worth re-validating.

## Limits / non-goals

- The canonicalizer is **not** a prompt linter. It does not check that all
  expected sections are *present* — only that present-and-known sections are
  in the canonical order. A separate "required sections" gate composes with
  this if you need it.
- Sections are atomic units; the canonicalizer never reorders content
  *within* a section.
- The default header regex is ATX markdown only. Authors using `<!-- section:
  foo -->` or other delimiters must pass `header_re=` (see source for the
  group(2)-is-the-key contract).
- The reserved key `__preamble__` is anchored at the top by design. If you
  want the preamble in a different position, refactor it into a real `#`
  section first.
