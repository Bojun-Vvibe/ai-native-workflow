# `citation-id-broken-link-detector`

Pure scanner for Markdown-style footnote citations in LLM-generated
documents. Catches the three failure modes that make "with sources"
output silently misleading:

1. **Missing definitions** — body references `[^foo]` but no
   `[^foo]: …` line exists. The reader sees a confident-looking
   citation marker that resolves to nothing.
2. **Orphan definitions** — `[^foo]: …` is defined but never
   referenced. Usually means the model deleted/rewrote the surrounding
   prose and left the source dangling.
3. **Duplicate-distinct definitions** — `[^foo]` is defined twice with
   *different* payloads. Verbatim repeats are harmless and are NOT
   flagged; distinct payloads are a real collision because the renderer
   silently picks one.

The detector is pure: no I/O, no clocks, no network. Stdlib-only Python.
Composes with `llm-output-trust-tiers` (set
`source_class="fresh"` and demote one rung when `has_broken=True`) and
`agent-decision-log-format` (one log line per scanned doc with the
`summary` field).

## SPEC

### API

```python
from citations import scan, CitationReport, CitationScanError

report = scan(markdown_text)        # CitationReport (frozen dataclass)
report.has_broken                   # bool: missing OR distinct-duplicate present
report.summary                      # one-line audit string
report.missing_definitions          # tuple[str, ...]
report.orphan_definitions           # tuple[str, ...]
report.duplicate_definitions        # dict[id, tuple[distinct_payload, ...]]
report.use_counts                   # dict[id, int]   how many times each ref appears in body
report.referenced_ids               # tuple[str, ...] first-seen order
report.defined_ids                  # tuple[str, ...] first-seen order
```

### Citation grammar (intentionally narrow)

- Reference (anywhere in body): `[^<id>]` where `<id>` matches
  `[A-Za-z0-9_\-]+`.
- Definition (start of line, with optional payload):
  `[^<id>]:<space><payload>` matching `^\[\^([A-Za-z0-9_\-]+)\]:[ \t]*(.+?)[ \t]*$`
  with `re.MULTILINE`.
- Definition lines are stripped from the body BEFORE the reference
  scan, so a definition does not also self-count as a reference.

### Invariants

1. A repeated-verbatim definition is NOT a duplicate
   (a doc may include the same footnote twice for layout reasons).
2. A reference repeated N times appears once in `referenced_ids` with
   `use_counts[id] == N`.
3. `has_broken` reflects only the two structural failures (`missing` or
   `distinct duplicate`). Orphans are reported but do NOT trip
   `has_broken` — an unused source is wasteful, not wrong.
4. `referenced_ids` and `defined_ids` are first-seen order, not
   lexicographic. This makes diffs against re-runs of the same doc
   stable.
5. `scan(non_str)` raises `CitationScanError`. The detector reports
   broken citations; it does not silently return an empty report on
   garbage input.

## Worked example output

```
$ python3 examples/example_1_missing_and_orphan.py
--- summary ---
refs=3 defs=3 missing=1 orphans=1 duplicates=0 has_broken=True
--- referenced (in first-seen order) ---
['vaswani', 'reprod-2024', 'never-defined']
--- defined (in first-seen order) ---
['vaswani', 'reprod-2024', 'orphan-note']
--- use_counts ---
{
  "never-defined": 1,
  "reprod-2024": 1,
  "vaswani": 2
}
--- missing_definitions ---
['never-defined']
--- orphan_definitions ---
['orphan-note']
--- duplicate_definitions ---
{}
--- has_broken ---
True
```

```
$ python3 examples/example_2_duplicate_definitions.py
--- summary ---
refs=3 defs=3 missing=0 orphans=0 duplicates=1 has_broken=True
--- duplicate_definitions ---
{
  "bench": [
    "https://example.org/bench-paper-A.pdf",
    "https://example.org/bench-paper-B.pdf"
  ]
}
--- missing_definitions ---
[]
--- orphan_definitions ---
[]
--- has_broken ---
True
OK
```

Both example scripts exit 0. Notice in example 2 that `[^verbatim]`
appears twice with the *same* URL and is correctly absent from
`duplicate_definitions`, while `[^bench]` appears twice with two
different URLs and is flagged.

## When to wire this in

- Right after the model returns a "with sources" or research-summary
  doc, before it goes to the trust-tier router.
- In CI for any docs-as-code repo where docs are LLM-drafted and the
  reviewer is human.
- As a quarantine signal in `llm-output-trust-tiers`:
  `has_broken=True` → demote one rung.

## When NOT to use

- Inline `[1]` (no `^`) or HTML `<sup>` citations — out of scope by
  design. Add a sibling detector if you need that grammar; do not
  loosen this regex (it would start matching prose like
  `[note: revised]`).
- Cross-document citation graphs (footnote in doc A, definition in doc B).
  This scanner is single-doc by design.
