# FM-01 — Context Rot

**Severity:** costly
**First observed:** early (this is the oldest pattern)
**Frequency in our ops:** weekly

## Diagnosis

The agent's context window fills with stale, irrelevant tool
outputs from the first half of the mission. By turn 30, the
agent is making decisions based on a context that's 70% noise.
Quality degrades gradually — there's no single bad turn, just a
slow drift toward worse choices.

## Observable symptoms

- Token-in count per turn climbs monotonically while task
  complexity does not.
- Cache-hit rate drops late in the session even though the
  system prompt and tools are unchanged.
- Late-mission turns reference files or facts the agent
  inspected 20+ turns earlier and clearly no longer remembers
  precisely.
- The agent re-reads files it already read, with slightly
  different excerpts each time.

## Mitigations

1. **Primary** — delegate exploration to sub-agents whose context
   never enters the parent. See
   [`sub-agent-context-isolation`](../../sub-agent-context-isolation/).
2. **Backstop** — aggressively truncate large tool outputs
   (file reads > N lines, command outputs > N bytes). The agent
   should re-fetch on demand, not carry the whole file forever.

## Related

FM-02 (Tool-call Storm), FM-05 (Cache Prefix Thrash).
