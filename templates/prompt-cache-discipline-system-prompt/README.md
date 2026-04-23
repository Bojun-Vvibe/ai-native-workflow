# Template: Prompt-Cache-Discipline System Prompt

A system prompt template and surrounding discipline for getting high
prompt-cache hit rates from coding agents on long-running missions.

## Why this exists

Modern coding agents on Anthropic, OpenAI, and Google models all support
some form of prompt caching: the provider hashes a stable prefix of your
prompt, stores its KV cache, and on subsequent requests within a TTL window
serves the cached portion at a fraction of the input-token price (typically
**10%** of standard input cost) and with much lower latency.

If you ignore this, every agent turn pays full input price to re-process
the same system prompt, the same tool definitions, and the same context
files. On a multi-hour mission with thousands of turns, this is the
difference between a $5 run and a $50 run.

Cache discipline is **almost free to adopt** — it costs only structural
discipline in how you assemble prompts. This template encodes the structure.

## The three principles

### 1. Stable prefix, append-only context

The prompt MUST be assembled in this fixed order:

```
[1] System prompt        ← never changes within a session
[2] Tool definitions     ← never changes within a session
[3] Long-lived context   ← changes rarely (charter, profile, repo overview)
[4] Mission state        ← grows append-only across turns
[5] Current turn input   ← the only "fresh" content per request
```

Anything that mutates in-place inside [1]–[3] kills the cache for the
remainder of the prompt. Examples of cache-killers:

- Putting the current timestamp in the system prompt header.
- Renumbering tool definitions when a new tool is conditionally added.
- Editing the charter mid-mission instead of appending an addendum.
- Re-summarizing past turns and replacing the originals.

### 2. Append-only history

When the conversation grows, new turns are *appended*. You do not rewrite
or compact prior turns. If the context window is filling up, prefer:

- A **summarization checkpoint** (write a checkpoint summary, start a
  new session with that checkpoint as the new [3] long-lived context),
  over
- An **in-place rewrite** (which destroys the cache and usually loses
  fidelity).

### 3. Cache-aware tool definitions

Tool definitions live in section [2] and must be **identical across turns
within a session**. Anti-patterns:

- Including only the tools "currently relevant" — defining the full set
  upfront and letting the model not call irrelevant ones is cheaper than
  recomputing the cache every time the toolset changes.
- Embedding per-call examples in the tool definition. Examples belong in
  section [3] or [5], not [2].
- Reordering tools alphabetically vs by-category between requests. Pick
  one order, stick to it.

## Files

- `system-prompt.template.md` — a concrete system prompt with the
  five-section structure laid out and inline notes on which lines are
  cache-stable. Paste into your coding agent's system prompt slot.
- `cache-economics-calculator.md` — a reference table of input/output
  pricing with and without cache for the major model families.

## When to use

- Long-running missions (>30 minutes wall clock).
- Missions with many WPs that share a stable prefix (PR triage,
  multi-file refactors, test generation across modules).
- Cost-sensitive workflows where the input/output ratio is heavily
  input-side.

## When NOT to use

- One-shot prompts (no second request to amortize the cache against).
- Workflows where the system prompt genuinely must change per turn
  (some tool-routing patterns). The cache discipline assumes stability;
  if you don't have it, faking it costs more than it saves.
- Models that don't support prompt caching at all (in 2026 this is
  rare, but check your provider's current docs).

## Adapt this section

- The system prompt template's tool definitions are placeholders. Replace
  with your actual tool schemas, in a fixed order, and never mutate
  during a session.
- The "long-lived context" section in the template loads charter +
  agent profile + repo overview. Adapt to whatever your mission needs,
  but keep that block stable for the whole session.
- The cache economics table is point-in-time. Cross-check against your
  provider's current pricing page before quoting numbers in cost
  estimates.
