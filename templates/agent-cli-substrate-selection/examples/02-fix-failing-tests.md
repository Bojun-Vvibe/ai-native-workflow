# Example 2 — Fix three failing tests in a TS module (agent, Clause 2)

## Task

> Three tests in `src/parser.test.ts` are failing after a refactor of `src/parser.ts`. Make them pass without weakening the assertions.

## Walking the rubric

- **Clause 1 — file discovery?** Partially. The two named files are known, but the failing tests reference helpers that may live in other files; the agent will need to follow imports. Already leaning agent.
- **Clause 2 — iterative refinement against ground truth?** **Yes, fires.** The success signal is `npm test` exiting zero. The fix loop is: read the failure, hypothesize, edit, re-run, observe new failure, refine. The loop *is* the value.

Stop. Class is `agent`.

## Substrate pick

From an installed inventory of `llm,aichat,claude,codex,opencode`, the chosen CLI is **`claude`**:

- Tool use over filesystem and shell, with file-edit primitives that diff-then-apply (lower risk than blind overwrites).
- Reasonable default for TS work.
- `codex` would be a perfectly fine alternate; preference order is environmental.

## What the prompt would emit

```json
{
  "class": "agent",
  "cli": "claude",
  "clause_fired": 2,
  "clause_evidence": "make 3 failing tests pass — success is npm test exit 0; the fix loop reads failures, edits, and re-runs",
  "confidence": "high",
  "note": "Clause 1 also lean-fires (imports may need following); Clause 2 wins since it's the structural reason"
}
```

## Mismatch shape we're avoiding

If we instead reached for `llm`:

- We'd `cat src/parser.ts src/parser.test.ts | llm -s "fix the failing tests"` and get back a code suggestion.
- We'd hand-apply the suggestion, run `npm test`, see two of three still failing, and either give up or paste the new failure back into another `llm` call. We are now manually being the agent loop — at human latency, with no tool isolation, accumulating context bloat across pastes.
- This is the **pipe-as-agent** failure mode from the README. Worse, the loop is so slow that we tend to over-edit per round to "save round trips," which makes diffs harder to review and easier to regress.

## Concrete invocation

```bash
# In the repo root, with claude already configured for this project
claude "Three tests in src/parser.test.ts are failing after a refactor of src/parser.ts. \
Make them pass without weakening the assertions. \
You may read any file in src/ and tests/. \
Run npm test after each meaningful change and use its output to drive your next edit. \
Do not modify the test file unless an assertion is provably wrong."
```

The agent loop now owns the run-test → read-failure → edit → re-run cycle. The human owns the boundary condition ("don't weaken assertions") and the final review. Task class matches substrate class.

## Where this could split

If the same agent loop also needs to refactor unrelated modules to fix the underlying root cause, you might split the task: one agent pass to fix the failing tests narrowly (this example), then a follow-up pre-agency pass to summarize what changed for a code-review writeup (Example 1's shape). That split is fine and is exactly what Clauses 2 + 3 + a sequential plan look like in practice.
