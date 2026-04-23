---
pr_number: 4242
pr_title: "fix: stop dropping cache breakpoints when assistant message ends with reasoning-only block"
repo: example-org/example-agent
author: example-author
url: https://github.com/example-org/example-agent/pull/4242
fetched_at: 2026-04-23
files_changed: 9
additions: 187
deletions: 41
focus_files:
  - src/provider/cache.ts
  - src/provider/cache.test.ts
note: "PR diff is 228 lines but ~70 of those are an unrelated lockfile bump. This review focuses on cache.ts (the substantive ~50 lines) and its test."
---

> Synthetic example. The repo, PR number, author, and code are
> illustrative — they do not refer to a real PR. The shape of the
> review is the point.

# Context

`example-agent` is a TypeScript coding agent that talks to multiple
LLM providers through a provider-abstraction layer. The cache layer
in `src/provider/cache.ts` decides where to insert cache-control
breakpoints in outgoing requests. On Anthropic, breakpoints are
explicit (`cache_control: {"type": "ephemeral"}`) and the provider
caps the number of breakpoints per request — so the layer must pick
the **right** four to keep, not just the first four it sees.

The bug this PR fixes is subtle: when the most recent assistant
message contains *only* reasoning blocks (a common shape on multi-turn
extended-thinking sessions), the existing breakpoint placer would
silently drop the breakpoint that was supposed to land on that
message's tail. The downstream effect is that the next turn pays
full input-token price for content that was already cached on the
prior turn — a billing regression that is hard to spot because the
agent's behavior is unchanged.

The bug matters more than its 30-line size suggests. On a long
extended-thinking session, the dropped breakpoint compounds: each
turn re-pays for prior reasoning, which on long sessions is the bulk
of the input. A user could see a 3–5× cost regression on these
sessions with no behavioral signal.

# Diff walkthrough

The substantive change is concentrated in two hunks of `cache.ts`.

**Hunk 1 — eligibility predicate (around line 84).** The original
code selected the breakpoint anchor by walking the message content
backward and stopping at the first `text` block:

```ts
const anchor = msg.content.findLast(p => p.type === "text");
if (anchor) anchor.cache_control = { type: "ephemeral" };
```

That is correct when the assistant message ends in text but wrong
when it ends with a reasoning block — the loop never finds an anchor
and the breakpoint is silently skipped. The fix broadens the
predicate to any cacheable part type, with reasoning explicitly
allowed:

```ts
const CACHEABLE: Part["type"][] = ["text", "reasoning"];
const anchor = msg.content.findLast(p => CACHEABLE.includes(p.type));
if (anchor) anchor.cache_control = { type: "ephemeral" };
```

The list is positively-scoped (allowlist of cacheable types), which
matches the lesson at the bottom of this review: deny-list-style
filters break silently when a new opaque block type is added; an
allowlist breaks loudly (the new type is not cached, but the loop
still terminates correctly).

**Hunk 2 — telemetry counter (around line 119).** A new
`breakpoints_dropped` counter is bumped whenever the eligibility
predicate matches no anchor. This is the right instrumentation
choice — the bug existed silently for months because nothing
counted the dropped breakpoints. The counter is exposed via the
existing `getMetrics()` surface; no new endpoint.

Hunks 3–9 are the lockfile bump and an unrelated formatting change
to `README.md`; not reviewed in detail.

# Test coverage

Two new tests in `cache.test.ts`:

- `T1: places breakpoint on text-tail message` — regression-guards
  that the original happy path still works after the predicate
  generalization.
- `T2: places breakpoint on reasoning-tail message` — the direct
  regression for the bug. Constructs a message whose only content is
  a reasoning block and asserts the breakpoint lands on it.

What's not covered:

- A message with **no** cacheable parts (e.g., only tool calls). The
  fix's behavior is correct (skip the breakpoint, bump the counter)
  but no test asserts it. Easy to add.
- The interaction with the request-level breakpoint cap. If the layer
  was previously relying on this hunk to drop a breakpoint, fixing
  the drop could push the request over Anthropic's 4-breakpoint
  ceiling, in which case some other breakpoint would now be silently
  dropped instead. No test exercises near-cap behavior.

# Risks

1. **Cap-collision regression.** If any caller assembled requests
   that relied on the drop-on-reasoning-tail behavior to stay under
   the 4-breakpoint ceiling, those callers will now hit the cap and
   the *last* breakpoint added will be dropped instead. Likelihood:
   low (the prior behavior was buggy and unlikely to have been
   intentionally relied upon), but worth a one-line check.
2. **Telemetry name collision.** `breakpoints_dropped` is a generic
   name. If a future hunk adds a different reason for dropping, the
   counter conflates causes. Consider `breakpoints_dropped_no_anchor`
   to leave room for `breakpoints_dropped_cap` later.
3. **No integration test.** The unit tests assert the breakpoint
   placement; no test asserts the actual cache-hit-rate improvement
   end-to-end. A regression that re-introduces the drop would still
   pass the unit tests if it does so by a different path (e.g., the
   anchor is set but later overwritten).

# Clarifying questions for the author

1. Is the lockfile bump intentional in this PR, or did it ride along
   from a `git pull` and should be split out for cleaner bisect?
2. Did you check call sites that build requests near the
   4-breakpoint cap? Specifically the long-context flow in
   `src/agents/longctx.ts` — that path looked like the most likely
   to be cap-bound.
3. Would you consider renaming the counter to
   `breakpoints_dropped_no_anchor` for future-proofing, as noted in
   risk 2?
4. Is there appetite for an integration test that asserts on
   `cache_read_input_tokens` from a real (or mocked-at-the-wire)
   Anthropic response? The unit tests are necessary but not
   sufficient.

# Verdict

**Ready to merge after Q&A.** The fix is correct and minimal; the
test coverage is appropriate for the unit-level regression. Two
small follow-ups would tighten it: split the lockfile bump (or
confirm it's intentional), and rename the counter for future-
proofing. Neither is a hard blocker. An integration test would be
nice but is reasonable to defer to a follow-up PR.

# What I learned

The durable lesson here is that **silent eligibility-failure bugs
in optimization layers are uniquely hard to catch** because the
program's behavior — the user-visible output — is unchanged when
they fire. Only a billing or latency signal reveals them, and those
signals are slow and aggregated. Two design moves prevent this
class: (1) every "find the X to optimize" loop should have a
counter for the case where it found nothing, exposed in the same
metrics surface as the optimization itself; (2) eligibility
predicates should be expressed as positive allowlists of types you
*do* want to include, not negative denylists of types you don't,
because allowlists fail loudly when a new type appears (the new
type is silently uncached — visible in the counter) while denylists
fail silently (the new type slips past the filter and hits the
optimization, possibly catastrophically). Both moves are cheap; the
second is structural and should be a default in any provider-shape
abstraction layer.
