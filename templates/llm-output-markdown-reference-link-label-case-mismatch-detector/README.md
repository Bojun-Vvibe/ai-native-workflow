# llm-output-markdown-reference-link-label-case-mismatch-detector

Pure-stdlib detector for **case-mismatched reference link labels** in
LLM Markdown output.

## Why this exists

CommonMark reference links match labels **case-insensitively** after
Unicode case folding and whitespace collapsing. So `[example][Foo]`
correctly resolves to `[foo]: https://example.com/`. Most renderers
do this silently — but it produces a real-world problem when the
output is consumed by:

- A documentation linter that does **byte-exact** label matching
  (some house style guides require it).
- A diff tool / search reviewer who scans for `[foo]:` and misses
  `[Foo]:` two pages later.
- A non-CommonMark renderer (some legacy Markdown engines, some chat
  preview cards) that *does* care about case.
- A human author trying to update the URL: they search for the label
  they just typed and fail to find the definition.

LLMs introduce this drift constantly because each occurrence is
generated independently and the model doesn't track exact casing.

The detector flags every reference label that has at least one
casing form different from the casing form used in its definition,
or where multiple references use mutually inconsistent casings.

There is an adjacent template
(`llm-output-link-reference-definition-orphan-detector`) that flags
references with no definition and definitions with no references.
This template is orthogonal: it presumes the label *resolves* and
asks whether the casing is consistent.

## When to use

- Markdown deliverables that use reference-style links heavily
  (long docs, large READMEs, design specs).
- After running the orphan detector. Together they cover both
  "missing" and "drifted" labels.

## How to invoke

```
python3 detect.py path/to/output.md
```

Exit codes:

- `0` — clean.
- `1` — at least one finding.
- `2` — usage / IO error.

Output (stable, sorted):

```
<line>:<col> <kind> label=<canonical> forms=<comma-list>
```

`kind` is one of:

- `reference_case_mismatch_with_definition` — the reference uses a
  casing different from the definition's casing. Reported once per
  reference occurrence.
- `multiple_definitions_different_case` — two or more `[label]:`
  definitions exist that fold to the same canonical label but use
  different byte casings. Reported once per extra definition.

`canonical` is the lowercased + whitespace-collapsed label, as the
CommonMark spec defines for matching.

## Worked example

`worked-example/bad.md` has:

- One definition `[Foo]: https://...` with two references `[Foo]`
  and `[foo]` — the second is a case mismatch.
- One label `[bar]: ...` plus `[Bar]: ...` — duplicate definitions
  with different casing.
- One label `[ok]: ...` with reference `[ok]` — clean, not flagged.
- A bracketed phrase that is **not** a reference link
  (`[just text]` with nothing after, no definition) — ignored.

Run:

```
python3 detect.py worked-example/bad.md
```

The output should match `worked-example/expected-output.txt` and
exit `1`.

## Non-goals

- Does not validate URLs.
- Does not warn about *whitespace* drift inside labels (e.g.
  `[foo bar]` vs `[foo  bar]`); CommonMark collapses internal
  whitespace, and treating that as drift would create noise.
- Does not handle nested or escaped brackets in labels. Real-world
  LLM output rarely uses them, and a strict CommonMark parser would
  itself reject most of those forms.
