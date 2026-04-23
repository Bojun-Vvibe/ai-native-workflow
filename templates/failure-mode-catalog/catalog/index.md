# Failure-mode catalog — index

Twelve seeded failure modes. Severity is from the operator's
perspective:

- **annoying** — wastes a few minutes, the agent eventually gets there
- **costly** — wastes tokens / time / a whole mission run
- **dangerous** — can ship a wrong-looking-right change

| ID    | Name                          | Severity   | Primary mitigation |
|-------|-------------------------------|------------|--------------------|
| FM-01 | Context Rot                   | costly     | sub-agent context isolation; trim tool outputs |
| FM-02 | Tool-call Storm               | costly     | per-turn tool budget; tool-output truncation |
| FM-03 | Schema Drift                  | dangerous  | agent-output-validation with `additionalProperties: false` |
| FM-04 | Premature Convergence         | dangerous  | scout-then-act mission; reviewer in implement-review loop |
| FM-05 | Cache Prefix Thrash           | costly     | prompt-cache-discipline; prompt-fingerprinting |
| FM-06 | Cross-repo Blindness          | dangerous  | multi-repo-monorepo-bridge with bridge-search |
| FM-07 | Stale Fork                    | dangerous  | oss-fork-hygiene weekly audit |
| FM-08 | Continuation Loop             | costly     | per-task continuation cap (N=3) → escalate |
| FM-09 | Silent Retry Multiplication   | costly     | track retries as separate ledger entries |
| FM-10 | Confident Fabrication         | dangerous  | reviewer agent + grep-the-claim verification |
| FM-11 | Lost Diff                     | dangerous  | per-task diff snapshot before next tool call |
| FM-12 | Output-fence Mishandling      | annoying   | strict JSON parse + repair_once |

## Reading order

If you only read three: FM-04 (Premature Convergence), FM-05
(Cache Prefix Thrash), FM-10 (Confident Fabrication). These are
the ones that produce the worst combination of "looks fine in the
log" and "wrong in production."

## How to extend

- Add new entries as `catalog/FM-NN-<short-name>.md`.
- Update this index in the same commit.
- Bump `frequency` annotations in existing entries quarterly based
  on how often you actually saw them.
