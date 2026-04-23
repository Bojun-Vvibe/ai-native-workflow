# PR review — four-question structural checklist

Run these four questions, in order, against any diff that touches
glue code (agent infrastructure, message brokers, ETL pipelines,
webhook fan-outs, event multiplexers, telemetry pipes). Each
question maps to a recurring bug shape that produces a **missing
output, not a wrong one** — exactly the failure mode that black-box
tests miss.

---

## 1. Every loop with a filter: does it return on the first match?

> If so, _is one match correct, or merely common?_

**Bug shape:** Early-return loop. The first match is the only one
processed; the tail is dropped.

**Where it hides:** Streaming-decode loops that bail on the first
non-synthetic block. Webhook routers that match the first handler.
Event filters that return the first hit instead of accumulating.

**Counter-question:** Is there a fixture where two matches occur in
sequence? If not, write one before approving.

---

## 2. Every "we're done" signal: is there a second signal that could lag?

> If so, what's the join condition?

**Bug shape:** Wrong-sync event. Code completes on the first
signal; the second signal's payload is dropped because the
listener is already torn down.

**Where it hides:** Stream completion (server-says-done vs
client-saw-final-chunk). Process exit (sigterm vs flush). Tool-call
completion (model emitted stop vs all parallel tool calls returned).
Multi-source aggregation that closes on first close.

**Counter-question:** Which signal is fast, which is slow, and what
happens if they swap on a slow network? If the answer is "the slow
one is dropped," the join is wrong.

---

## 3. Every translator: what does the default branch do?

> If it passes through, which source values is that wrong for?

**Bug shape:** Non-portable enum default-passthrough. A switch /
match / dict-get falls through with the source value as the
destination value. Some source values are not valid destination
values, so they leak through and break a downstream consumer that
expected a closed enum.

**Where it hides:** Provider-string translators (anthropic /
openai / gemini → internal). Role mappers (user / assistant /
system / tool → internal). Status code mappers. File extension to
mime type mappers. Any place where the destination type is "smaller"
than the source type.

**Counter-question:** Enumerate the source domain. Enumerate the
destination domain. Are there source values not in the destination
domain? If yes, the default branch is wrong for those.

---

## 4. Every constructor: are there other constructors?

> Do they attach the same cross-cutting concerns? Where's the test
> that asserts they do?

**Bug shape:** Drifted second constructor. Object can be built two
ways (e.g. `from_config` and `from_env`, or `new()` and
`from_existing()`). One path attaches a cross-cutting concern
(metrics hook, logger, lifecycle callback, telemetry tag); the
other path silently doesn't.

**Where it hides:** Classes with both a default constructor and an
`from_*` factory. Builders with a fast path and a hydrated path.
Session objects rebuilt from snapshot vs created fresh. Anywhere
"there are two ways to make this thing" is true.

**Counter-question:** Grep for every call site that produces an
instance. Is there a test that exercises each call site? Does any
production-only call site lack a test? If yes, the second
constructor is the candidate for drift.

---

## How to use this checklist

- **Self-review (before push):** read each question while the diff
  is on screen. Five minutes max.
- **Review of someone else's PR:** drop a finding per question that
  fires. Phrase as a question, not an assertion.
- **In a meeting:** read each question aloud. The act of saying
  "every loop with a filter" while looking at a `for ... if ...
  return` block is enough to surface most question-1 hits.

## What this does not catch

- **Wrong** outputs (swapped fields, miscalculated sums,
  plausible-but-wrong strings). Use property-based tests or a
  domain expert.
- Style, naming, formatting. Use a linter.
- Architectural fit. Use a longer-form review template.

## Source

[_Four bug shapes from this week's PR reviews_](https://github.com/Bojun-Vvibe/ai-native-notes/blob/main/posts/2026-04-24-four-bug-shapes-from-this-weeks-pr-reviews.md)
