# Worked example: 0% → 87% cache hit rate on a 30-turn agent session

A realistic before/after on a long-running code-review agent. Numbers
are representative; your model + prompt sizes will shift them.

## Setup

- Provider: Anthropic, `claude-sonnet-4-5`.
- Mission: agent reviews 30 PRs sequentially, one per turn.
- Prompt regions per turn:
  - System prompt: 1.2k tokens
  - Tool defs: 0.8k tokens
  - Long-lived context (charter, repo overview, glossary): 18k tokens
  - Mission state (grows): starts ~0, ends ~14k
  - Current turn (the PR diff + ask): 2–6k tokens

## Before — naive assembly

What the engineer wrote on day 1:

```python
def build_prompt(turn_idx, pr):
    return [
        {"role": "system", "content": f"Today is {datetime.utcnow().isoformat()}. "
                                      f"You are a careful reviewer (turn {turn_idx})."},
        {"role": "system", "content": REPO_OVERVIEW},
        {"role": "system", "content": CHARTER},
        # tools generated freshly each call, dict order non-deterministic
        # ... tool defs ...
        # ... mission state ...
        {"role": "user", "content": pr.diff_and_ask},
    ]
```

Cache-relevant problems, all classic:

1. `datetime.utcnow().isoformat()` in the system prompt → first byte
   of the prompt rotates every second. Cache never warms.
2. Turn index in the system prompt → prompt prefix mutates per turn.
3. Tool defs serialized from a Python dict without `sort_keys=True` →
   field order can shift, invalidating cache.
4. No `cache_control` markers anywhere → Anthropic does not cache
   without explicit breakpoints.

Cost over 30 turns:

| Region | Tokens / turn | Turns | Total tokens | $/MTok | Cost |
|---|---|---|---|---|---|
| System+tools | 2.0k | 30 | 60k | $3.00 | $0.18 |
| Long-lived context | 18.0k | 30 | 540k | $3.00 | $1.62 |
| Mission state (avg) | 7.0k | 30 | 210k | $3.00 | $0.63 |
| Current turn | 4.0k | 30 | 120k | $3.00 | $0.36 |
| Output | 1.5k | 30 | 45k | $15.00 | $0.68 |
| **Total** | | | | | **$3.47** |

Wall time: ~6.5 s/turn × 30 = ~3 min 15 s.

## After — cache-aware assembly

Refactor:

```python
SYSTEM_PROMPT = "You are a careful reviewer. Always cite file:line."  # frozen
TOOLS = sorted_tool_defs()  # deterministic, included in full every turn

def build_prompt(pr, mission_state):
    return dict(
        system=[{"type": "text", "text": SYSTEM_PROMPT,
                 "cache_control": {"type": "ephemeral"}}],
        tools=TOOLS,
        messages=[
            {"role": "user", "content": [
                {"type": "text", "text": REPO_OVERVIEW + CHARTER + GLOSSARY,
                 "cache_control": {"type": "ephemeral"}}]},
            *as_messages(mission_state, breakpoint_on_last=True),
            {"role": "user", "content": pr.diff_and_ask},
        ],
    )
```

Changes:

- Timestamp gone from the prompt. (Pass it via tool result if a tool
  needs it.)
- Turn index gone from the prompt.
- Tool defs sorted, included in full every turn.
- Three explicit `cache_control` breakpoints: system, long-lived
  context, mission-state tail.

Cost over the same 30 turns:

| Region | Tokens / turn | Cache reads | Cache writes | Fresh | Effective $/MTok | Cost |
|---|---|---|---|---|---|---|
| System+tools | 2.0k × 30 | 2.0k × 29 = 58k | 2.0k × 1 | 0 | mostly $0.30 | $0.018 |
| Long-lived context | 18.0k × 30 | 18.0k × 29 = 522k | 18.0k × 1 | 0 | mostly $0.30 | $0.165 |
| Mission state (tail-cached) | 7.0k × 30 | ~5.5k × 29 = 160k | small writes | small | blended $0.60 | $0.13 |
| Current turn | 4.0k × 30 | 0 | 0 | 120k | $3.00 | $0.36 |
| Output | 1.5k × 30 | — | — | 45k | $15.00 | $0.68 |
| **Total** | | | | | | **$1.35** |

Wall time: ~2.4 s/turn × 30 = ~1 min 12 s.

## Results

| Metric | Before | After | Delta |
|---|---|---|---|
| Cost (30 turns) | $3.47 | $1.35 | **−61%** |
| Wall time | 3 min 15 s | 1 min 12 s | **−63%** |
| Cache hit rate | 0% | 87% | — |
| Model behavior | baseline | indistinguishable | — |

The 87% hit rate is **input tokens served from cache / total input
tokens**. The remaining 13% is the per-turn diff + question, which
is genuinely fresh content and not cacheable.

## Lessons

- Removing the timestamp was the single biggest win — it took the
  cache hit rate from 0% to ~50% by itself.
- Sorting tool defs took it from ~50% to ~70%. Cheap fix, big lever.
- Adding the breakpoint after the long-lived context took it from
  ~70% to ~87%. The remaining gap is fundamental.
- **No prompt-engineering changes.** Same instructions, same tools,
  same outputs. Pure assembly discipline.
