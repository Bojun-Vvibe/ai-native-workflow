# `multi-turn-context-prune-by-relevance`

Pure pruner that fits a multi-turn conversation history into a token
budget by dropping the LOWEST-relevance turns first — not the oldest.
The naive "drop oldest N" approach loses the original task spec and the
load-bearing tool result that the model still needs; this template
keeps them by structurally pinning three classes of turn and ranking
the rest by a caller-supplied relevance scorer.

## SPEC

### Pins (always kept, in priority order)

1. **System prompt** — any turn with `role="system"`.
2. **Latest user turn** — the most recent `role="user"` turn (the one
   the model is about to answer).
3. **Caller-pinned turns** — any turn with `pinned=True` (load-bearing
   tool results, long-form specs, "remember this" answers).

If the pinned turns alone exceed `budget_tokens`, `prune` raises
`PruneError`. Silent over-budget output would defeat the entire point.

### Eviction order

Among non-pinned turns, eviction is sorted by:

1. **Lowest `relevance` first** (caller-supplied `(turn) -> float`).
2. **Older first** as the tiebreak — recency is a tiebreak signal, not
   the primary signal.

Turns are dropped one at a time until the projected token total fits
the budget.

### API

```python
from pruner import Turn, prune, PruneResult, PruneError

result = prune(
    turns=[Turn(turn_id="t0", role="system", text=..., tokens=30), ...],
    budget_tokens=4096,
    relevance_score=lambda turn: cosine(embed(turn.text), embed(latest_user_text)),
)
result.kept_ids        # tuple[str, ...] in original order
result.dropped_ids     # tuple[str, ...] in eviction order (lowest first)
result.kept_tokens     # int  (always <= budget_tokens after a successful prune)
result.dropped_tokens  # int
result.pin_reasons     # {turn_id: "system" | "latest_user" | "explicit_pin"}
result.advice          # "fits" | "tight" | "summarize_dropped"
```

`tokens` is caller-supplied — wire your real tokenizer (or the same
heuristic you use in `tool-call-cost-estimator`) on the way in.

`relevance_score` is INJECTED. Common choices:

- Embedding cosine vs the latest user turn (semantic relevance).
- LLM rubric returning `0..1` (slow but interpretable).
- Recency-weighted keyword overlap with the latest user turn.
- A constant `0.5` if you only want the structural pins to do work.

### Invariants

1. `kept_tokens <= budget_tokens` after a successful prune.
2. Every system turn and the most recent user turn appear in
   `pin_reasons` and `kept_ids`.
3. `pinned=True` turns appear in `pin_reasons` with reason
   `"explicit_pin"` and are kept regardless of relevance.
4. `kept_ids` preserves original conversation order.
5. `dropped_ids` is in eviction order (lowest relevance first), so the
   first-dropped turn is the one the caller most likely wants to feed
   into a `conversation-summarizer-window`.
6. Duplicate `turn_id`, negative `tokens`, unknown `role`, and
   `budget_tokens <= 0` all raise `PruneError`.
7. `advice` is `"summarize_dropped"` whenever any turn was evicted —
   the caller is expected to either replace the dropped span with a
   summary turn or accept context loss explicitly.

## Worked example output

```
$ python3 examples/example_1_drop_off_topic_first.py
--- input: 7 turns, total 208 tokens ---
--- budget: 160 tokens ---

kept_ids:      ['t0', 't1', 't3', 't4', 't6']
dropped_ids:   ['t5', 't2']  (eviction order: lowest relevance first)
kept_tokens:   153
dropped_tokens:55
advice:        summarize_dropped
pin_reasons:   {
  "t0": "system",
  "t6": "latest_user"
}

OK
```

The off-topic detour `t5` (relevance 0.05) is evicted first; the
clarifying question `t2` (relevance 0.4) is evicted second. The system
prompt and the latest user turn are pinned; the original task `t1`, the
zone info `t3`, and the recommendations `t4` survive on relevance.

```
$ python3 examples/example_2_explicit_pin_and_overbudget.py
--- (a) explicit pin keeps low-score tool result ---
kept_ids:    ['s', 'tr1', 'u2']
dropped_ids: ['u1', 'a1']
kept_tokens: 78 / budget 90
pin_reasons: {
  "s": "system",
  "tr1": "explicit_pin",
  "u2": "latest_user"
}
advice:      summarize_dropped
(a) OK

--- (b) pinned-over-budget raises ---
raised as expected: pinned turns alone require 710 tokens, budget is 300
(b) OK
```

Scenario (a) demonstrates the load-bearing-tool-result case: `tr1` has
relevance 0.05 (lowest in the conversation) but is pinned, so it
survives while higher-scoring turns are dropped. Scenario (b)
demonstrates the structural failure: when the pins alone don't fit, the
pruner raises rather than silently returning over-budget output —
caller decides whether to climb to a bigger model, summarize the pin,
or fail the request.

## When to wire this in

- Right before the next model call, after computing relevance once
  against the latest user turn.
- As the producer side of `conversation-summarizer-window` — the
  `dropped_ids` list is exactly the input the summarizer should
  collapse into one elided-summary turn.
- As an input signal to `agent-cost-budget-envelope` — `kept_tokens`
  drives the per-call cost estimate.

## When NOT to use

- Conversations where every turn is structurally required (codegen
  with running file context). Use a summarizer or a bigger model
  instead — pruning will drop necessary state.
- When you don't have a credible relevance signal. A degenerate
  scorer (random, or always 1.0) makes this no better than
  drop-oldest, and worse because it hides the failure.
