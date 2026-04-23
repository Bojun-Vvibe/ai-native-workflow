# FM-11 — Lost Diff

**Severity:** dangerous
**First observed:** any agent that edits files in long sessions
**Frequency in our ops:** rare but high-impact when it happens

## Diagnosis

The agent edits a file, then later in the same session edits the
file again — but the second edit is based on a stale view of the
first edit's result. The second edit clobbers the first. The
working tree ends up with neither change applied correctly, or
worse, with one change applied to the *wrong place* because the
agent's mental model of the file diverged from the file on disk.

Common trigger: the agent reads a file, edits it, then makes
several other tool calls (grep, bash) before editing the same file
again — without re-reading. The agent edits against its memory of
the file, not its current state.

## Observable symptoms

- `git diff` shows changes that don't match the agent's narrative
  ("I added X then refined it to Y"; the diff shows only X
  partially overwritten).
- Edit operations whose `old` string isn't found in the current
  file content — usually the agent had to retry several times.
- Reviewer comments like "this looks like two PRs collided in
  one file."
- Tests that pass in the agent's claim but fail in CI.

## Mitigations

1. **Primary** — orchestrator snapshots the diff after every
   write/edit; before the *next* edit to the same file, force a
   re-read tool call. Make this a turn-level invariant.
2. **Secondary** — a reviewer agent pass that diffs the final
   tree against the claimed sequence of changes. Discrepancy →
   reject.

## Related

FM-01 (Context Rot — same root cause: agent's memory of the world
diverging from the world).
