# FM-04 — Premature Convergence

**Severity:** dangerous
**First observed:** early
**Frequency in our ops:** weekly

## Diagnosis

The agent commits to a hypothesis or a plan in turn 2 — usually
based on a confident but shallow read of the task description —
and then spends the rest of the mission marshaling evidence for
that plan instead of testing it. New information that contradicts
the early hypothesis is rationalized away.

This is not "the model is overconfident." It's structural: once
the agent has written the plan into its own context, the plan
becomes part of the priors for every subsequent turn.

## Observable symptoms

- Plan emitted on turn 1 or 2; plan never edited despite later
  discoveries.
- Late-mission tool calls all confirm the plan; none challenge
  it.
- The final diff implements the plan but does not address the
  user's actual underlying problem — which a later human review
  catches in 30 seconds.
- "Looks fine" reviewer comments from the implementing agent on
  its own work.

## Mitigations

1. **Primary** — use [`scout-then-act-mission`](../../scout-then-act-mission/):
   a read-only scout produces a structured findings report, then
   a separate actor commits to a plan based on the scout's
   findings. The actor does not have the early-convergence
   pressure.
2. **Secondary** — pair an implementer with a different reviewer
   in
   [`multi-agent-implement-review-loop`](../../multi-agent-implement-review-loop/).
   Different agents fail differently; a reviewer is more likely
   to catch a plan the implementer locked in too early.

## Related

FM-10 (Confident Fabrication — premature convergence often
manifests as fabricated justifications late in the mission).
