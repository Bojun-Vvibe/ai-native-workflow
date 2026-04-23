# Template: Scout-then-Act mission

A two-agent mission pattern: a **scout** does pure read-only research first,
then an **actor** receives the scout's findings and performs the change. The
scout is forbidden from writing; the actor is forbidden from independent
research. The handoff is a single structured artifact.

## Why this pattern exists

When you ask one agent to "explore the codebase and then make the change,"
two failure modes dominate:

1. **Premature writing.** The agent starts editing before it has read
   enough. The first edit anchors its mental model and subsequent reading
   only confirms what it already wrote.
2. **Conflated context.** By the time the agent gets to the editing step,
   its context is full of half-relevant exploration. The actual change
   happens in a noisy context, and the diff reflects that noise.

Splitting research from action forces the scout to **commit to a written
finding** before any code is touched. The actor then operates from a clean
context with only the scout's report as background. This trades one extra
agent invocation for substantially better diffs on unfamiliar codebases.

## When to use

- Editing an **unfamiliar codebase** where you don't know which file owns
  the behavior you need to change.
- **Cross-cutting changes** that touch concerns spread across modules.
- **Bug investigation** where the root cause is unknown and might not be
  in the file the symptom appears in.
- **Migration / rename** missions where the scout's job is to enumerate
  occurrences and the actor's job is to apply the change.

## When NOT to use

- The change is **obvious and local** — `templates/agent-profile-conservative-implementer/`
  on its own is sufficient.
- The codebase is **small enough to fit in one context** — splitting adds
  overhead with no readability win.
- **Greenfield work** — there's nothing to scout.
- Tasks where the scout's report would be longer than the actual change.
  At some point the report IS the work; just do the change.

## Files

- `mission.example.yaml` — wires scout and actor with a strict handoff
  contract.
- `prompts/scout.md` — read-only research agent prompt.
- `prompts/actor.md` — change-execution agent prompt.
- `examples/sample-run.md` — a realistic transcript on a synthetic but
  representative bug-hunt task.

## The handoff contract

The scout MUST produce a single artifact at `findings.md` with a fixed
structure:

```
## Question
<the question the scout was asked to answer>

## Answer
<the scout's direct answer in one paragraph>

## Evidence
- file:line — quoted snippet — why it's relevant
- file:line — ...

## Confidence
high | medium | low

## Recommended action
<concrete steps the actor should take>

## Out of scope
<what the scout looked at and decided was NOT relevant, with one-line
reason each — prevents the actor from re-investigating these>
```

The actor MUST treat `findings.md` as the only source of truth for the
research. It MAY read the files cited in Evidence to confirm context, but
MUST NOT broaden its exploration. If the actor finds the scout's report
insufficient, the correct response is to **stop and request a second
scout pass**, not to silently widen the investigation.

## Adapt this section

- Scout's `confidence` thresholds — by default, `low` confidence triggers
  a second scout pass before any actor invocation. Tune for your risk
  tolerance.
- Actor's "stop and request second scout" trigger — by default, fires if
  the actor hits a file not mentioned in `findings.md`. Some workflows
  prefer a softer "warn and continue".
- Whether scout and actor share a model. By default they don't — using
  different models produces more diverse findings and reduces shared
  blind spots.
