# FM-02 — Tool-call Storm

**Severity:** costly
**First observed:** early
**Frequency in our ops:** occasional

## Diagnosis

The agent enters a tight loop of small tool calls — usually `read`,
`grep`, `glob` — without making any visible progress between
calls. Each call is cheap, but the loop runs 50+ times. The agent
is "thinking with tools" instead of thinking, often because it has
no internal model of the codebase and is using the tool surface as
a substitute.

## Observable symptoms

- `tool_calls` per turn > 8 sustained for many turns.
- The same file is read more than once with no edits between reads.
- `grep` patterns that progressively narrow without producing a
  visible action ("find FooBar" → "find FooBar in src" → "find
  FooBar in src/util" → no edit).
- Wall-clock time per turn dominated by tool latency, not model
  latency.

## Mitigations

1. **Primary** — set a per-turn tool-call budget in the
   orchestrator (e.g., 8 calls). On overrun, force a planning
   turn that summarizes findings before the next tool call.
2. **Secondary** — surface "files already read this session" to
   the agent in a sidebar. If it's about to re-read, that's a
   prompt it should consult its prior summary instead.

## Related

FM-01 (Context Rot — same root cause, different symptom),
FM-04 (Premature Convergence — sometimes the agent storms tools
*because* it converged on a wrong plan early).
