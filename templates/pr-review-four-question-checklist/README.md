# Template: PR review — four-question structural checklist

A short, opinionated **structural checklist** for reviewing pull
requests against agent infrastructure (and any other code that is
mostly glue: message brokers, ETL pipelines, webhook fan-outs,
event multiplexers, telemetry pipes). Four questions, run in order,
each tied to a specific bug shape that recurs in this kind of code.

This is **not** a style checklist. It says nothing about naming,
formatting, or commit hygiene. It is also not the long-form
[`oss-pr-review-template`](../oss-pr-review-template/) — that
template produces a 2–4 page learning artifact per PR. This
template produces **one paragraph of structured findings** in
under five minutes, suitable for a real review comment or a
self-review pass before you open your own PR.

The four questions are derived from a four-bug-shape taxonomy
([source post](https://github.com/Bojun-Vvibe/ai-native-notes/blob/main/posts/2026-04-24-four-bug-shapes-from-this-weeks-pr-reviews.md))
synthesized from a week of real OSS reviews against agent
infrastructure repos. Each shape produces a **missing output, not a
wrong one** — a tail dropped, a chunk lost, a field omitted, a hook
unregistered — which is exactly the failure mode that black-box
tests miss and that careful code review catches.

## Why this exists

Three problems this template addresses:

1. **"Careful review" is unevenly distributed.** Some reviewers
   spot the structural shapes; some don't. The same reviewer spots
   them on Tuesday but misses them on Friday. A four-line checklist
   is the cheapest way to make review uniform across people and
   across days.
2. **Reviewers default to behavioral inspection.** They run the
   tests, skim the diff, look for obvious bugs. The four shapes
   here are **structural** — none of them can be found by running
   the code. They are found by reading the loop, the wait, the
   default branch, the second constructor.
3. **Self-review is the weakest review.** The author of the change
   is least likely to catch these shapes because they wrote the
   code with the structure that hides them. Running the checklist
   against your own diff before you push catches roughly half of
   what a fresh reviewer would catch later.

## What's in this template

| File | Purpose |
|---|---|
| `README.md` | This document. |
| `CHECKLIST.md` | The four questions, in canonical form. Drop into a repo as `.github/PR_REVIEW_CHECKLIST.md` or paste into a review comment. |
| `prompts/agent-checklist.prompt.md` | LLM prompt: run the four-question checklist against a unified diff and emit a structured finding per question. |
| `bin/run-checklist.sh` | Thin wrapper that pipes a `git diff` into a configured agent CLI with the prompt. Exit non-zero if any question fires. |
| `examples/` | Three worked examples — one per repo family — showing each question firing on a real-shaped diff and the resulting finding. |

## The four questions

Verbatim from the source post:

1. **Every loop with a filter:** does it return on the first match?
   If so, _is one match correct or merely common?_
2. **Every "we're done" signal:** is there a second signal that
   could lag? If so, what's the join condition?
3. **Every translator:** what does the default branch do? If it
   passes through, which source values is that wrong for?
4. **Every constructor:** are there other constructors? Do they
   attach the same cross-cutting concerns? Where's the test that
   asserts they do?

Each question maps to a recurring bug shape:

| # | Bug shape | What goes missing |
|---|---|---|
| 1 | Early-return loop | Tail elements after the first match |
| 2 | Wrong-sync event | One signal completed; the laggy second signal's payload is dropped |
| 3 | Non-portable enum default-passthrough | Source values that the translator silently forwards as-is when they should have been translated |
| 4 | Drifted second constructor | Cross-cutting concerns (logging, metrics, hook registration) attached to constructor A but not B |

## How to use

### As a self-review pass before you push

```bash
# from your feature branch
git diff origin/main...HEAD | \
  bash ~/templates/pr-review-four-question-checklist/bin/run-checklist.sh
```

The script emits a finding per question that fires, and exits
non-zero if any do. You can wire it into a `pre-push` hook (see
[`guardrail-pre-push`](../guardrail-pre-push/)) for a soft warning
— do not make it a hard block, since false positives at this
granularity are intentional (the checklist is meant to make you
think, not to gate).

### As an LLM-assisted reviewer pass on someone else's PR

```bash
gh pr diff <PR_NUMBER> --repo <owner>/<repo> | \
  bash ~/templates/pr-review-four-question-checklist/bin/run-checklist.sh
```

The output is structured Markdown — you read it, decide which
findings are real, and either drop the real ones into a review
comment as-is or use them as scaffolding for a longer
[`oss-pr-review-template`](../oss-pr-review-template/) review.

### As a paper checklist in a review meeting

Print `CHECKLIST.md`. Read each question aloud while the diff is
on screen. This sounds primitive. It works. The act of saying
"every loop with a filter" out loud while looking at a
`for ... if ... return` block is enough to surface most instances
of question 1 without an LLM in the loop.

## What this template does not do

- It does not replace tests. The four shapes are catchable in
  review, but the durable fix is a regression test per shape (a
  two-element list test for question 1, a two-event test for
  question 2, a per-enum-value test for question 3, a
  per-constructor-path test for question 4). The checklist is the
  shorter feedback loop; the tests are the longer one.
- It does not generalize beyond glue code. Tight algorithmic code,
  data-structure internals, numerics, and rendering code have
  different recurring bug shapes. This checklist is calibrated
  against agent infrastructure, message brokers, ETL pipelines, and
  webhook fan-outs. Use a different checklist (or grow this one)
  for other domains.
- It does not catch _wrong_ outputs, only _missing_ ones. A bug
  that swaps two field values, miscalculates a sum, or returns a
  plausible-but-wrong string is invisible to all four questions.
  Those bugs need property-based tests or a domain expert.

## Composes with

- [`oss-pr-review-template`](../oss-pr-review-template/) — when a
  finding from this checklist is interesting enough to warrant a
  long-form learning artifact, promote it. The four-question pass
  is the triage; the long-form review is the synthesis.
- [`failure-mode-catalog`](../failure-mode-catalog/) — that
  template catalogs runtime failure modes; this one catalogs
  structural source-code shapes that produce them. Two views of
  the same surface.
- [`guardrail-pre-push`](../guardrail-pre-push/) — wire
  `bin/run-checklist.sh` as a soft pre-push warning to surface
  findings before review.

## Calibration notes

- After a week of running this on agent-infra PRs, expect roughly
  half of question-1 hits and a third of question-2 / question-3 /
  question-4 hits to be real bugs. The other hits are intentional
  early-returns, single-signal completions, default-allow
  translators, or constructors that genuinely don't share concerns.
  False positive rate is acceptable at this volume because each
  finding takes under thirty seconds to dismiss.
- Question 4 has the lowest hit rate but the highest fix value when
  it does fire. A second constructor that drifted from the first
  often hides bugs that survived months of testing because no test
  exercised that construction path.
- The order of questions matters. Question 1 is first because
  early-return loops are the most common shape and the cheapest to
  spot. Question 4 is last because it requires reading two
  separated regions of the file and comparing them.

## See also

- Source post: [_Four bug shapes from this week's PR reviews_](https://github.com/Bojun-Vvibe/ai-native-notes/blob/main/posts/2026-04-24-four-bug-shapes-from-this-weeks-pr-reviews.md)
- Long-form review template: [`oss-pr-review-template`](../oss-pr-review-template/)
- Failure-mode catalog: [`failure-mode-catalog`](../failure-mode-catalog/)
