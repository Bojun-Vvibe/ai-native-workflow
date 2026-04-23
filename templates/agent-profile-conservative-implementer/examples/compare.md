# Comparison: conservative vs aggressive profile on the same task

**Task** (identical for both runs):

> Add a `--dry-run` flag to the `sync` CLI command. When set, the command
> should log every action it would take but not perform any writes.

**Codebase context**: a small CLI repo. The `sync` command is implemented in
`src/commands/sync.ts` and performs three side-effecting operations: writing
local cache files, calling a remote upload API, and updating a local manifest.
The repo has no existing dry-run convention. There are unit tests for `sync`
that exercise the happy path with mocked side effects.

---

## Run A — Conservative Implementer profile

**Diff**: `src/commands/sync.ts` (+22, -3), `src/commands/sync.test.ts` (+18, -0).
Total: +40, -3 across 2 files.

**Behavior**:

- Adds a `--dry-run` flag via the existing flag-parsing helper used by every
  other command in the file.
- Wraps each of the three side-effecting calls in a small `if (!dryRun)` gate.
- When `dryRun` is true, logs the action that would have been taken using the
  same logger the command already uses.
- Adds two new tests: one asserting the cache file is written when the flag
  is absent, one asserting it is *not* written when the flag is set.
- Surfaces three explicit assumptions: (a) dry-run logs go to the same
  logger, not stderr; (b) the API client's no-op mode wasn't used because
  the request was for surface-level gating, not request-level mocking;
  (c) the exit code in dry-run mode is 0 even when "would have failed"
  conditions are detected — flagged for confirmation.

**Reviewer experience**: 5 minutes to read; obvious correctness; merges as-is
or with one tweak (the exit code assumption).

---

## Run B — Hypothetical "aggressive implementer" profile

**Diff**: 8 files changed, +287, -94. Includes:

- `src/commands/sync.ts` rewritten to use a new `Effect` abstraction (a class
  the agent introduced) that wraps each side effect in a runnable that can
  be executed or just described.
- New file: `src/effects/Effect.ts` (+76 lines).
- New file: `src/effects/index.ts` (+12 lines).
- `src/commands/upload.ts` and `src/commands/manifest.ts` migrated to use
  the new `Effect` abstraction "for consistency."
- `src/utils/logger.ts` changed to add a `dryRunPrefix` option, with all
  existing callsites updated.
- Two existing tests rewritten to use the new abstraction; one deleted as
  "no longer relevant"; three new tests added for the abstraction itself.
- Adds a runtime dependency on `chalk` to colorize the dry-run output.

**Reviewer experience**: 45 minutes to read. Three concerns immediately:

1. The `Effect` abstraction wasn't asked for and changes how every command
   in the repo handles side effects. This is a load-bearing architectural
   choice that needs its own design discussion, not a side effect of a
   `--dry-run` request.
2. A test was deleted. Even if the agent's reasoning is correct, a deleted
   test in a CLI repo is a red flag that requires manual verification of
   coverage parity.
3. A new dependency (`chalk`) was added without being mentioned in the
   description.

The reviewer either rejects the PR and asks for a minimal version, or
spends an hour negotiating the scope down. Either way, the cost of getting
the dry-run flag shipped has tripled.

---

## Side-by-side

| Dimension | Conservative | Aggressive |
|---|---|---|
| Files touched | 2 | 8 |
| Net lines | +40 / -3 | +287 / -94 |
| New deps | 0 | 1 (chalk) |
| Tests deleted | 0 | 1 |
| Tests added | 2 | 3 (different code paths) |
| Assumptions surfaced | 3 explicit | 0 explicit |
| Reviewer time | ~5 min | ~45 min |
| Likelihood of merge round-trip | low | high |
| Coverage of original ask | 100% | 100% |

The two diffs solve the same user-facing problem. The conservative diff
preserves the option to introduce an `Effect` abstraction later as a
deliberate, separately-reviewed change. The aggressive diff couples a
small feature to an unrequested architectural change, which is the
single most common failure mode for unsupervised AI coding work.

## When you actually want the aggressive profile

Not on this task. But there are tasks where it's right: greenfield
projects, conscious refactors where sweeping is the point, and prototyping
loops where you're the only reviewer. Use it deliberately, not by default.
