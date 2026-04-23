# FM-07 — Stale Fork

**Severity:** dangerous
**First observed:** as soon as we maintained ≥3 OSS forks
**Frequency in our ops:** monthly (per audit)

## Diagnosis

A fork of an upstream OSS project sits unsynced for months. The
agent, asked to "fix the bug," edits the fork — but upstream has
already fixed the bug, deprecated the surrounding API, and moved
on. The agent reproduces work, opens an irrelevant PR, or worse,
ships a "fix" against a function that no longer exists upstream.

## Observable symptoms

- `git log upstream/main..main` is empty but `git log
  main..upstream/main` is hundreds of commits.
- Agent's PR doesn't apply against upstream `main` (merge
  conflicts, or "file not found").
- Agent confidently references upstream code that was deleted
  6 months ago.
- Maintainer feedback: "we already fixed this in #1234."

## Mitigations

1. **Primary** — adopt [`oss-fork-hygiene`](../../oss-fork-hygiene/);
   run `audit-forks.sh` monthly and `sync-fork.sh` before every
   contribution session.
2. **Backstop** — refuse to dispatch a contribution mission
   against a fork that is >30 days behind upstream. Sync first,
   then dispatch.

## Related

FM-04 (Premature Convergence — agent commits to "fix this here"
based on a stale base).
