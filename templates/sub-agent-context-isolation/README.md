# sub-agent-context-isolation

A pattern for keeping a long-running parent agent fast and on-task by
delegating exploratory or noisy work to **sub-agents whose context
never enters the parent's context window**. The parent only ever sees
the sub-agent's final structured answer, not the 50 file reads, 12
greps, and 3 retries it took to produce it.

## When to use this

- The parent agent's context is becoming a bottleneck: latency
  growing turn-over-turn, prompt-cache hit rate dropping, or the
  parent starting to forget earlier turns.
- A subtask is **search-shaped**: "find the file that defines X",
  "list all callers of Y", "summarize what this module does". The
  intermediate evidence is large; the answer is small.
- A subtask requires reading code or docs the parent will never need
  to quote verbatim later.
- You want to run several investigations **in parallel** without
  serializing them through one context window (pairs well with
  `parallel-dispatch-mission`).

## When NOT to use this

- The subtask is small enough that the read+answer fits in a single
  cheap turn (delegation overhead > savings).
- The parent will need to **quote or reason about the raw evidence
  later** — sub-agent isolation throws that evidence away. Use a
  scratch-file pattern instead (parent reads file when needed).
- The subtask requires multi-turn user interaction — sub-agents
  should be one-shot.
- You don't have a way to enforce isolation (no Task tool, no
  sub-agent runtime). Don't fake it by just "asking the model to
  pretend"; the tokens still go through.

## The pattern

```
Parent agent
  |
  |-- (long-lived context: mission, plan, decisions, recent results)
  |
  |-- delegate("find every call site of fooBar()")
  |       \
  |        Sub-agent (fresh context)
  |        - reads 40 files
  |        - runs 6 greps
  |        - 14 turns of reasoning
  |        - returns: ["src/a.ts:42", "src/b.ts:113", "test/c.ts:8"]
  |       /
  |<-- only the 3-line answer enters parent context
  |
  |-- continues planning with the answer, not the evidence
```

Two rules make this work:

1. **Parent never sees sub-agent intermediate turns.** The runtime
   must support this (Claude Code's `Task` tool, OpenCode's `task`,
   spec-kitty's worker dispatch, custom orchestrator with separate
   context windows). Pretending via prompt instructions doesn't
   count — the tokens still flow.
2. **Sub-agent returns a tight structured answer**, not a narrative.
   Define the output schema in the dispatch prompt. The smaller and
   more structured the answer, the more isolation pays off.

## Anti-patterns

- **Delegating with no schema.** Sub-agent returns 800 tokens of
  prose ("I looked at this file, then this one, here's what I
  noticed..."). Parent's context bloats anyway. Always specify the
  output shape.
- **Re-asking the parent to "now read those files yourself"** after
  the sub-agent already read them. You just paid twice and lost the
  isolation benefit.
- **Cascading delegation without depth limits.** Sub-agent spawns
  sub-sub-agents which spawn sub-sub-sub-agents. Each level adds
  latency and failure surface. Cap at 1 level deep unless you have
  measurement showing deeper helps.
- **Using sub-agents for tasks the parent could cache-hit.** If the
  parent already has the relevant context warm, dispatching to a
  cold sub-agent costs more than just answering.
- **Letting the sub-agent return its raw chain-of-thought.** Even
  if you want some reasoning visible, structure it as a `rationale`
  field, not free-form epilogue.
- **Trusting sub-agent answers blindly for high-stakes decisions.**
  Sub-agents fail silently more than parents do because the parent
  doesn't see the failure mode. Pair with verification when stakes
  are high.

## Files

- `prompts/dispatch-template.md` — copy-paste template for the
  parent's call to a sub-agent. Specifies role, scope, output
  schema, and what NOT to return.
- `prompts/sub-agent-system-prompt.md` — system prompt to give the
  sub-agent. Enforces brevity, structured output, and refusal to
  speculate beyond the evidence it actually read.
- `examples/find-call-sites.md` — worked example: parent dispatches
  "find all call sites of `processInvoice()`"; shows the dispatch
  message, what the sub-agent did internally (10 turns, ~14k
  tokens), and the 4-line answer that enters the parent context.
- `examples/comparison-without-isolation.md` — same task done
  without delegation, showing the parent's context grew by ~14k
  tokens and the cache hit rate dropped from 82% to 61% on the
  next turn.

## Worked example summary

| approach | parent context Δ | parent next-turn cache hit | total tokens billed | wall time |
|---|---|---|---|---|
| with sub-agent isolation | +280 | 82% | 14,200 | 9.2s |
| without (parent does it) | +13,940 | 61% | 13,800 | 7.1s |

The "without" path is slightly cheaper in absolute tokens (no
sub-agent system prompt overhead) and slightly faster (no dispatch
round-trip). The **savings show up on the next 5+ turns** of the
parent: lower latency per turn, fewer cache evictions, and the
parent doesn't get distracted by the noisy intermediate evidence.

If your mission is one-shot, isolation is overhead. If your mission
runs 30+ turns and does many investigations, isolation compounds.

## Related

- `parallel-dispatch-mission` — when you want N sub-agents running
  concurrently, not serially.
- `scout-then-act-mission` — when the parent itself needs to scout
  first; sub-agents are for delegating individual scout sub-questions.
- `cache-aware-prompt` — pairs naturally; the sub-agent's system
  prompt should also be cache-friendly if it's reused.
