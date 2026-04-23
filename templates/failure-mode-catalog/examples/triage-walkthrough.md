# Triage walkthrough — three real failed runs

How an operator with this catalog open triages three failed
mission runs in under five minutes each.

## Run #1 — "agent kept reading the same files"

**Symptom (operator-visible):** Mission ran 4× longer than usual.
Final commit was good but cost 3.2× the typical mission of this
type.

**Operator opens the per-turn token-in chart from
`token-budget-launchd`.** Sees:
- `tool_calls` per turn: 4, 6, 9, 11, 13, 14, 15, 16, ...
- Tokens-in per turn: monotonically rising
- The same 3 files appear in tool-call logs across 12 different
  turns

**Triage:** symptoms match FM-01 (Context Rot) and FM-02
(Tool-call Storm). Both share a root cause; the operator picks
FM-01's primary mitigation.

**Action:** Re-dispatch as a scout-then-act mission. Scout's
findings are extracted into a fresh actor context, which never
sees the 12 redundant reads. Mission completes in baseline cost.

## Run #2 — "PR description references a function that doesn't exist"

**Symptom:** Reviewer comment: "Where is `validate_payload()`
defined? I can't find it anywhere in the diff or in the existing
code."

**Operator greps:** `bridge-search.sh validate_payload ~/work-bridge`
returns no results. Function does not exist anywhere.

**Triage:** Open the agent's transcript. The agent claimed
`validate_payload()` was defined in `src/api/middleware.py`. There
is no tool call in the transcript reading that file. The agent
cited a path it never opened.

**Pattern:** FM-10 (Confident Fabrication). 30 seconds of grep
disproved a confident claim.

**Action:** Reject the PR. Re-dispatch the mission with the
implement-review loop: a separate reviewer is required to
grep-verify every file path in the implementer's PR description.

## Run #3 — "mission keeps making 'almost done' progress"

**Symptom:** Mission has been running for 90 minutes; cost is at
$8 and rising. Operator checks the handoff ledger:

```
T-step-2          partial   continuation: "continue from line 142"
T-step-2.cont-1   partial   continuation: "continue from line 142"
T-step-2.cont-2   partial   continuation: "continue from lines 142, 198"
T-step-2.cont-3   partial   continuation: "continue from lines 142, 198"
```

**Triage:** Three continuations on the same parent task, each
nearly identical. Pattern is FM-08 (Continuation Loop).

**Action:** The orchestrator's N=3 cap should have triggered;
verify it's enabled. Force-escalate the parent task as
`unrecoverable` with reason `continuation_loop_overflow`. Open
the offending file (`src/retry.py`) manually; the issue is that
lines 142 and 198 use a context-manager pattern the agent's
mitigation pattern doesn't fit. Re-scope by hand: rewrite those
two sites with a different pattern, then re-dispatch.

## What this walkthrough demonstrates

In none of the three cases did the operator need to "debug the
prompt." The catalog provided a name within the first minute, and
the named mitigation was the action. Without the catalog, each
of these would have taken 30+ minutes of "let me look at the
transcript and see what happened."
