# `llm-output-heading-trailing-period-detector`

Pure-stdlib detector for **ATX Markdown headings ending in
terminal sentence punctuation** (`.`, `!`, `?`):

```
## Why this matters.
### Conclusion!
#### Open questions?
```

Headings are titles, not sentences. Every major style
guide that bothers to take a position (Google, GitLab, MDN,
Chicago for headings) forbids trailing terminators on
headings. LLMs introduce them constantly because their
training data is mostly running prose where every clause ends
with one.

Three finding kinds:

- `trailing_period`        — `.` (the dominant case)
- `trailing_exclamation`   — `!`
- `trailing_question_mark` — `?`

Trailing whitespace and the optional ATX closing hashes
(`## Heading ##`) are stripped before the punctuation check,
so `## Heading. ##` and `## Heading.   ` both fire.

**Ellipsis is exempt.** `…` (U+2026) and ASCII `...` at end of
heading carry deliberate "more to come" semantics common in
slide decks, so they are NOT flagged. If your house style
forbids ellipsis on headings, layer a separate detector on
top — do not weaken this one.

Setext headings (underlined with `===` / `---`) are out of
scope. They are rare in LLM output and have a different shape;
mixing them in here would force the detector to look across
multiple lines and complicate the per-line contract.

Fenced code blocks (` ``` ` and `~~~`) are skipped wholesale,
so a tutorial about heading style does not self-trigger.

Abbreviation-style trailing periods (`v1.0.`, `Mr.`, `etc.`)
are still flagged at heading position. The right fix at
heading position is "drop the period", not "preserve the
abbreviation".

## When to use

- Pre-publish gate on any LLM-generated **doc-site page**,
  **README**, **runbook**, **release note**, or **PR
  description** before it is merged. Trailing terminators on
  headings are the single most common stylistic regression in
  LLM-authored Markdown.
- Inside a **review-loop validator**: each finding's
  `(line_number, level, terminator)` triple is small and
  deterministic, so the same finding twice in a row across
  repair attempts is a clean "give up and escalate" signal.
- As a **template-rendering postcondition**: when a prompt
  template enumerates section titles, the model frequently
  echoes them back with a `.` appended. This detector catches
  that drift before it reaches a human reviewer.

## Usage

```
python3 detector.py [FILE ...]   # FILEs, or stdin if none
```

Exit code: `0` clean, `1` at least one finding. JSON to stdout.
Pure stdlib; no third-party deps.

## Composition

- `agent-output-validation` — feed the JSON `findings` array
  into a repair prompt verbatim. Each entry's `heading_text`
  is enough context for the model to identify the offender
  without re-reading the whole document.
- `llm-output-atx-heading-trailing-hash-detector` — orthogonal:
  that template targets *unwanted closing hashes*, this one
  targets *unwanted closing punctuation*. Run both for full
  ATX-heading hygiene.
- `llm-output-markdown-heading-skip-level-detector` — run after
  this one in a doc-quality pipeline; punctuation is cheaper to
  fix than structural level skips, so failing fast on
  punctuation tightens the repair loop.

## Worked example

Input is `worked-example/input.md` — planted issues across all
three kinds, plus negative cases for ellipsis (both `…` and
`...`), fenced blocks, missing space after `#`, and 7-hash
non-headings.

```
$ python3 detector.py worked-example/input.md
```

Verbatim output is captured in
`worked-example/expected-output.txt` (exit code `1`, 7
findings):

- line 3  level 2 — `trailing_period`        — `Why this matters.`
- line 7  level 3 — `trailing_exclamation`   — `Conclusion!`
- line 11 level 4 — `trailing_question_mark` — `Open questions?`
- line 15 level 5 — `trailing_period`        — `Closing hashes too.` (closing `##` stripped)
- line 19 level 6 — `trailing_period`        — `v1.0.` (abbreviation still flagged)
- line 46 level 2 — `trailing_period`        — first heading after a fence
- line 54 level 2 — `trailing_period`        — trailing spaces stripped before check

Notes on what is **NOT** flagged (intentionally):

- `## Slide-style heading…`  — Unicode ellipsis is intentional.
- `## Three-dot ellipsis...` — ASCII three-dot ellipsis ditto.
- `## Clean heading`         — no terminator at all, fine.
- Headings *inside* fenced blocks at lines 38–41 and 50–52 —
  fences are skipped wholesale.
- `#NotAHeading.`            — no space after `#`, not an ATX
  heading per CommonMark.
- `####### TooDeep.`         — 7 hashes, not a valid ATX
  heading (max is 6).

## Files

- `detector.py` — pure-stdlib detector + JSON renderer + CLI
- `worked-example/input.md` — planted-issue input
- `worked-example/expected-output.txt` — captured exit + JSON
- `README.md` — this file

## Limitations

- Setext headings are out of scope; they need a two-line lookup
  and a different shape of finding.
- Question marks at end of FAQ headings are flagged. Many FAQ
  styles deliberately end every Q with `?`. If that is your
  house style, configure your CI to ignore `trailing_question_mark`
  findings rather than weakening the detector globally.
- Trailing colons (`## Note:`) are NOT in scope. Colons on
  headings are common and stylistically defensible (they
  introduce a list or a parenthetical). A colon-on-heading
  detector belongs in a separate template.
- Right-to-left text (Arabic, Hebrew) where the visual
  terminator appears at the *start* of the line is flagged
  correctly because we operate on logical character order, not
  visual order — but verify against your renderer if mixed-RTL
  headings are common in your docs.
