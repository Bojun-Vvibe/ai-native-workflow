# llm-output-conventional-commit-subject-validator

Pure-stdlib validator for **Conventional Commits 1.0.0 subject lines**
embedded in markdown emitted by an LLM. When an agent proposes a
commit message inside a fenced shell or git block (e.g.
`git commit -m "..."` or a `gitcommit` block), the subject is the
contract that downstream tooling — release-please, semantic-release,
conventional-changelog, in-house bump scripts — reads to decide what
gets a minor/patch/major bump and what shows up in the changelog. A
subject that drifts from the spec breaks all of them silently, by
miscategorising or skipping the change.

## Why a separate template

Adjacent templates do not cover this:

- `commit-message-trailer-pattern` validates *trailers* (`Signed-off-by:`,
  `Refs:`) at the bottom of a commit body. It says nothing about the
  subject line.
- `llm-output-fence-extractor` extracts fenced code generically; it
  does not validate semantics.
- `llm-output-markdown-fenced-code-language-tag-validator` validates
  the language tag itself, not the contents inside it.
- The 200+ markdown / JSON detectors flag rendering hazards. None of
  them speak the Conventional Commits grammar.

## What it catches

Per subject extracted from a fenced block, the validator emits one or
more of these findings:

| kind | what it catches |
|---|---|
| `missing_type` | no `:` in the subject, so no type prefix can be parsed |
| `unknown_type` | type is not in the allowed set (`feat fix docs style refactor perf test build ci chore revert`) |
| `empty_scope` | `feat(): ...` — parens with nothing inside |
| `scope_whitespace` | scope contains spaces or tabs |
| `missing_colon_space` | colon not followed by exactly one space before the description |
| `empty_description` | nothing after the colon-space |
| `trailing_period` | description ends with `.` |
| `subject_too_long` | subject exceeds 72 chars (the widely-followed soft cap) |
| `leading_capital` | description starts with an uppercase letter |
| `breaking_marker_misplaced` | `!` appears somewhere other than right before the colon |

## Where it looks for subjects

The validator is **code-fence-aware** and only looks inside fenced
code blocks whose info-string first token (case-insensitive) is one of:

- `bash` / `sh` / `shell` / `zsh` / `console` — extracts `-m "<subject>"`
  / `-m '<subject>'` / `--message=...` from any line containing
  `git commit`. Quote-handling supports backslash-escaped quotes.
  Multiple `-m` flags on one line yield multiple subjects.
- `git` / `gitcommit` / `commit` — pulls the first non-empty,
  non-`#`-comment line as the subject (the canonical commit-message
  file shape). Body lines after that are ignored.

Everything outside a recognised fence is ignored. A subject mentioned
in prose (e.g. inline backticks) is not flagged — by design, this
is a validator of *proposed shell commands*, not a freeform linter.

## Design choices

- **Quote-aware extractor.** `_extract_dash_m_subjects` walks the line
  one char at a time, tracking quote state and `\\"` / `\\'` escapes.
  It does not use `shlex` (which would error on unbalanced quotes
  emitted by partial LLM output); it reports nothing for unterminated
  quotes.
- **One pass, deterministic.** Findings sorted by `(line_no, kind, subject)`.
- **Soft cap configurable.** Default 72; pass `max_len=` to `detect()`
  to override per-project.
- **Pure function.** `detect(src) -> CommitSubjectReport`. No I/O,
  no clocks, no transport.
- **Stdlib only.** `dataclasses`, `json` (only for serialising the
  report), `sys`. No `re`, no `shlex`, no third-party parser.

## Composition

- `commit-message-trailer-pattern` — orthogonal; run alongside this
  validator if your agent also emits commit bodies with trailers.
- `llm-output-markdown-fenced-code-language-tag-validator` — run first
  so that `gitcommit` blocks are tagged correctly. An untagged commit
  block is invisible to this validator by design.
- `llm-output-fenced-code-language-tag-missing-detector` — same idea,
  upstream tagger sanity check.

## Worked example

`bad/example.md` plants seven hazards across one `bash` block (six
`git commit -m` invocations) and one `gitcommit` block:

1. no type prefix and trailing period — `Add new feature.`
2. scope whitespace — `feat(  user): add login flow`
3. unknown type — `feet: typo in type`
4. missing colon-space — `feat:no space after colon`
5. breaking-marker misplaced — `fix!(api): bang in wrong place`
6. empty scope — `chore(): empty scope`
7. unknown (capitalised) type in `gitcommit` block — `Refactor: simplify the loader!`

`good/example.md` has four well-formed subjects across the same
block tags (including a valid `refactor!: ...` breaking-change marker).

### Running the validator

```
$ python3 detector.py bad/example.md good/example.md
=== bad/example.md ===
{
  "fences_inspected": 7,
  "findings": [
    {
      "detail": "no ':' found; cannot parse a type prefix",
      "kind": "missing_type",
      "line_no": 7,
      "subject": "Add new feature."
    },
    {
      "detail": "scope `  user` contains whitespace",
      "kind": "scope_whitespace",
      "line_no": 8,
      "subject": "feat(  user): add login flow"
    },
    {
      "detail": "type `feet` is not in the allowed set (build, chore, ci, docs, feat, fix, perf, refactor, revert, style, test)",
      "kind": "unknown_type",
      "line_no": 9,
      "subject": "feet: typo in type"
    },
    {
      "detail": "colon must be followed by exactly one space before the description",
      "kind": "missing_colon_space",
      "line_no": 10,
      "subject": "feat:no space after colon"
    },
    {
      "detail": "`!` must appear immediately before the `:`",
      "kind": "breaking_marker_misplaced",
      "line_no": 11,
      "subject": "fix!(api): bang in wrong place"
    },
    {
      "detail": "`()` is present but contains no scope",
      "kind": "empty_scope",
      "line_no": 12,
      "subject": "chore(): empty scope"
    },
    {
      "detail": "type `Refactor` is not in the allowed set (build, chore, ci, docs, feat, fix, perf, refactor, revert, style, test)",
      "kind": "unknown_type",
      "line_no": 18,
      "subject": "Refactor: simplify the loader!"
    }
  ],
  "ok": false,
  "subjects_checked": 7
}
=== good/example.md ===
{
  "fences_inspected": 4,
  "findings": [],
  "ok": true,
  "subjects_checked": 4
}
exit=1
```

The bad doc trips seven distinct findings spanning six different rule
kinds; the good doc passes silently. Exit code is 1 if any input has
findings, 0 otherwise — usable in pre-commit / CI without further wiring.

## Counts

- bad/: 1 markdown file, 7 subjects checked, 7 findings (6 distinct kinds)
- good/: 1 markdown file, 4 subjects checked, 0 findings

## Non-goals

- This is **not** a full Conventional Commits parser. It does not
  validate footers / `BREAKING CHANGE:` body lines / linked issue
  references; that's `commit-message-trailer-pattern`'s territory.
- It does not enforce a project-specific scope allowlist; only that
  whatever scope is given is well-formed.
- It does not opine on imperative vs past-tense mood.
- It does not check for duplicate subjects across the doc.
