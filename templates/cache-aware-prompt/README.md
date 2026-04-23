# Template: Cache-aware prompt assembly

A tactical template for **assembling each individual API request** so it
maximizes prompt-cache hits across the major providers (Anthropic
explicit cache breakpoints, OpenAI automatic prefix caching, Google
implicit context caching). Includes the request shape, the things that
silently invalidate caches, snippets for the most common SDKs, and an
instrumentation pattern so you can actually see your hit rate.

> Sibling template: [`prompt-cache-discipline-system-prompt`](../prompt-cache-discipline-system-prompt/)
> covers the **system-prompt + mission-design** side. This one covers
> the **per-request assembly + measurement** side. Use both.

## Why this exists

Cache hits are typically billed at **10%** of normal input price and
are **much** lower latency. On a multi-turn agent session of even
modest length, the difference between "I assembled the prompt
correctly" and "I assembled it sloppily" can be 5–10× cost and 2–3×
wall-time, with **no** change to model behavior.

The mistake almost everyone makes the first time: putting something
that mutates per-turn (a timestamp, a turn counter, a tool list whose
order depends on availability) **above** the bulk of the static
content. One byte changing high in the prompt invalidates everything
below it. Cache-aware assembly is the discipline of keeping the
mutating bytes at the bottom.

## When to use

- Any **multi-turn** agent loop (>3 turns) hitting the same provider.
- Any mission where the **same system prompt + tool defs + context
  files** are sent on every turn.
- Any production system where **input tokens dominate** cost (almost
  all agentic systems).
- Batch jobs where you'll send N requests sharing a long prefix
  (evaluation harnesses, document-by-document analysis, RAG over a
  fixed corpus).

## When NOT to use

- **One-shot** completions where you'll never re-send the prefix.
- Cases where the **prefix is shorter than the cache minimum** —
  Anthropic requires a minimum cacheable block size (currently
  ~1024 tokens for most models, ~2048 for some); below that the
  `cache_control` directive is silently ignored.
- Workloads where **freshness > cost** (e.g., the prompt MUST embed
  live market data at the top — you've intentionally accepted a 0%
  cache hit rate for correctness).

## Anti-patterns

- **Timestamp in the system prompt header.** Classic. `Today is
  2026-04-23 14:32:01` rotates every second; cache never warms.
  Fix: pass timestamp as a tool result or a turn input, not as
  prompt content.
- **Renumbered or reordered tool definitions.** "I'll only include
  the `web_search` tool when the user asks about news." The tool
  block changed → everything after it is uncached. Fix: include all
  tools every turn; let the model decide.
- **Mutable JSON serialization order.** Python `dict` → JSON without
  `sort_keys=True` reorders fields; the prefix bytes change; cache
  misses. Fix: deterministic serialization for anything in the
  cacheable region.
- **Per-turn user-id / session-id strings high in the prompt.** Move
  them to the bottom or pass as metadata, not prose.
- **Forgetting the cache breakpoint.** On Anthropic, you must
  explicitly mark `cache_control: {"type": "ephemeral"}` on the
  block you want cached. No marker → no cache.
- **More than 4 cache breakpoints (Anthropic).** The provider caps
  the number of explicit breakpoints. Excess markers are ignored —
  but not always the ones you'd hope. Use a small fixed budget:
  one after system, one after tools, one after long-lived context,
  one after mission state.
- **Expecting cache to survive >5 minutes idle.** TTL is usually 5 min
  (Anthropic standard) — extendable to 1 hr at extra cost. Long human
  pauses cool the cache. If you know a pause is coming, send a
  cheap keep-alive request.

## The canonical request shape

Assemble every request in this exact order. Mark cache breakpoints at
the four boundaries marked `[BP]`.

```
[ 1 ] system prompt
[ 2 ] tool definitions
                                  [BP-1]  ← cache up to here
[ 3 ] long-lived context
        - charter / profile
        - repo overview
        - glossary
                                  [BP-2]  ← cache up to here
[ 4 ] mission state (append-only)
        - prior turns
        - tool results
        - artifacts
                                  [BP-3]  ← cache up to here
[ 5 ] current turn input
        - the single new user message
        - any per-turn metadata
                                  [BP-4]  ← cache up to here (optional)
```

The first three breakpoints are the cost wins. BP-4 is only useful if
you re-issue the same turn (retries, structured-output reformat).

## Files

- `snippets/anthropic-cache-control.py` — request-builder snippet for
  the Anthropic SDK with explicit cache breakpoints.
- `snippets/openai-prefix-stable.py` — request-builder snippet for
  OpenAI; OpenAI uses automatic prefix caching, so the discipline is
  about not mutating the prefix.
- `snippets/google-implicit-cache.py` — Gemini implicit context
  caching; same prefix-stability discipline plus the explicit-cache
  alternative.
- `snippets/cache-hit-instrument.py` — wraps any of the above to log
  per-turn cache hit rate to a JSONL file you can chart.
- `examples/before-after.md` — a real before/after on a 30-turn agent
  session: 0% → 87% cache hit rate, 6.2× cost reduction, no behavior
  change.

## Adapt this section

- Cache breakpoint count — defaults to 4 (Anthropic max). If you're on
  OpenAI or Google, breakpoints are not explicit; instead the
  discipline is the bytewise-stable-prefix part.
- TTL — defaults to standard (5 min). Switch to extended (1 hr) only
  if your idle gaps are real and you've measured the cost crossover.
- Long-lived context size — keep it small enough that the cache write
  cost (typically 1.25× normal input on first miss) is amortized over
  enough hits. A 50k-token context block needs ~5 hits to break even.
