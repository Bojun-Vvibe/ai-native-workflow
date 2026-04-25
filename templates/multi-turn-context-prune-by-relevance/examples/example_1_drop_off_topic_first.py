"""Example 1: a 7-turn conversation pruned to a tight budget.

Pins keep the system prompt and the latest user turn.
Lowest-relevance turns are dropped first; ties break older-first.
"""
import json
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from pruner import Turn, prune  # type: ignore


# Build a realistic 7-turn history. tokens are caller-supplied (real
# tokenizer in prod). relevance here is hand-set to make the example
# legible, but in prod this could be embedding cosine vs the latest user
# turn, an LLM rubric, or recency-weighted keyword overlap.
turns = [
    Turn("t0", "system",    "You are a careful research assistant.",       30, pinned=False),
    Turn("t1", "user",      "Help me plan a backyard veggie garden.",       20),
    Turn("t2", "assistant", "Sure — what's your climate zone?",             15),
    Turn("t3", "user",      "Zone 7b, 6h direct sun.",                      18),
    Turn("t4", "assistant", "Great. Tomatoes, peppers, and beans...",       60),
    # an off-topic detour that the model itself opened — low relevance now
    Turn("t5", "assistant", "By the way, did you know cucumbers are 96% water?", 40),
    # latest user turn -- always pinned
    Turn("t6", "user",      "Given the above, what should I plant first?",  25),
]

# Hand-built relevance: higher = more relevant to the latest user turn.
RELEVANCE = {
    "t0": 1.0,    # system (pinned anyway)
    "t1": 0.9,    # original task
    "t2": 0.4,    # clarifying question (somewhat redundant now)
    "t3": 0.95,   # zone info still load-bearing
    "t4": 0.8,    # actual recommendations
    "t5": 0.05,   # off-topic detour
    "t6": 1.0,    # latest user (pinned anyway)
}


def relevance(t: Turn) -> float:
    return RELEVANCE[t.turn_id]


# Total tokens = 30+20+15+18+60+40+25 = 208. Budget = 160 forces ~48 tokens dropped.
BUDGET = 160

result = prune(turns, BUDGET, relevance)

print(f"--- input: {len(turns)} turns, total {sum(t.tokens for t in turns)} tokens ---")
print(f"--- budget: {BUDGET} tokens ---")
print()
print(f"kept_ids:      {list(result.kept_ids)}")
print(f"dropped_ids:   {list(result.dropped_ids)}  (eviction order: lowest relevance first)")
print(f"kept_tokens:   {result.kept_tokens}")
print(f"dropped_tokens:{result.dropped_tokens}")
print(f"advice:        {result.advice}")
print(f"pin_reasons:   {json.dumps(result.pin_reasons, indent=2, sort_keys=True)}")

# Structural checks: budget honored, pins kept, off-topic detour evicted first.
assert result.kept_tokens <= BUDGET, "must fit budget"
assert "t0" in result.kept_ids, "system must be pinned"
assert "t6" in result.kept_ids, "latest user must be pinned"
assert "t5" in result.dropped_ids, "off-topic detour should be evicted first"
assert result.dropped_ids[0] == "t5", "lowest-relevance turn must be FIRST in eviction order"
assert result.advice == "summarize_dropped"
print()
print("OK")
