# FM-08 — Continuation Loop

**Severity:** costly
**First observed:** when we introduced agent-handoff-protocol
**Frequency in our ops:** rare but expensive when it happens

## Diagnosis

A worker returns `status: partial` with a continuation. The
orchestrator dispatches the continuation. The continuation worker
also returns `partial`, with a continuation that's nearly
identical to the previous one. Repeat. The mission burns through
its budget making "almost done" claims forever.

Root cause is usually: the continuation's "next task" instruction
is too vague, so the new worker re-does most of the previous
worker's analysis before realizing it can't make further progress
either.

## Observable symptoms

- ≥3 continuations on the same parent task.
- Each continuation handoff lists nearly the same
  `context_pointers` as the prior one.
- Tokens-in per continuation does not decrease (would be expected
  if work were progressing).
- The `human_summary` repeats the same hedging phrasing across
  continuations.

## Mitigations

1. **Primary** — cap continuations per parent task at N=3 in the
   orchestrator (see
   [`agent-handoff-protocol`](../../agent-handoff-protocol/)
   routing rules). On overflow, escalate as
   `unrecoverable_reason: continuation_loop_overflow`.
2. **Secondary** — require continuation `next_task.instruction`
   to be *more specific* than the parent's instruction (mention
   line numbers, file names, exact remaining cases). Reject
   handoffs whose continuation is just a paraphrase.

## Related

FM-04 (Premature Convergence — sometimes the loop is the agent
trying to escape an earlier wrong commitment).
