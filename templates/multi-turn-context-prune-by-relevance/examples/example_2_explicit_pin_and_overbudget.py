"""Example 2: explicit pin saves a low-relevance turn; pinned-over-budget raises.

Two scenarios:
  (a) An assistant turn carries a load-bearing tool-result the caller
      MUST keep even though its surface relevance is low. `pinned=True`
      is honored regardless of score.
  (b) Pinned turns alone exceed the budget — prune raises PruneError
      rather than silently returning over-budget output.
"""
import json
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from pruner import Turn, prune, PruneError  # type: ignore


# --- (a) explicit pin overrides low relevance score ---
turns = [
    Turn("s",   "system",    "You answer concisely.",                            20, pinned=False),
    Turn("u1",  "user",      "Look up the customer's account tier.",             15),
    # tool result -- low surface relevance to the latest question, but the
    # caller knows it's load-bearing for the answer the model is about to write.
    Turn("tr1", "tool",      "tier=enterprise, seats=412, region=eu-west",       40, pinned=True),
    Turn("a1",  "assistant", "Account is enterprise tier with 412 seats.",       25),
    Turn("u2",  "user",      "OK -- can they enable SSO without sales?",         18),
]

# everything except tr1 looks more relevant on its surface
def relevance_a(t):
    return {"s": 1.0, "u1": 0.6, "tr1": 0.05, "a1": 0.7, "u2": 1.0}[t.turn_id]

# total = 20+15+40+25+18 = 118; budget 90 forces dropping ~28 tokens
res_a = prune(turns, 90, relevance_a)
print("--- (a) explicit pin keeps low-score tool result ---")
print(f"kept_ids:    {list(res_a.kept_ids)}")
print(f"dropped_ids: {list(res_a.dropped_ids)}")
print(f"kept_tokens: {res_a.kept_tokens} / budget {res_a.budget_tokens}")
print(f"pin_reasons: {json.dumps(res_a.pin_reasons, indent=2, sort_keys=True)}")
print(f"advice:      {res_a.advice}")
assert "tr1" in res_a.kept_ids, "explicit pin must keep tool result even at relevance 0.05"
assert res_a.pin_reasons["tr1"] == "explicit_pin"
# u1 has higher relevance than a1? no -- u1 is 0.6, a1 is 0.7; lowest unpinned = u1 (0.6)
# u1 is 15 tokens; dropping it saves 15 -> total 103, still > 90; next victim a1 (0.7) -> 78
assert "u1" in res_a.dropped_ids and "a1" in res_a.dropped_ids
print("(a) OK")
print()

# --- (b) pinned alone exceeds budget -> PruneError ---
big_pinned = [
    Turn("s",   "system", "long boilerplate system prompt... " * 5, 200),
    Turn("u",   "user",   "tiny ask",                                10),
    Turn("p",   "tool",   "huge required tool result " * 8,         500, pinned=True),
]
def relevance_b(t):
    return 0.5

print("--- (b) pinned-over-budget raises ---")
try:
    prune(big_pinned, budget_tokens=300, relevance_score=relevance_b)
    print("FAIL: expected PruneError")
    sys.exit(1)
except PruneError as e:
    print(f"raised as expected: {e}")
    assert "pinned turns alone require" in str(e)
print("(b) OK")
