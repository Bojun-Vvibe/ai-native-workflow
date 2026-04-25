"""multi-turn-context-prune-by-relevance — pure pruner.

When a multi-turn conversation history is about to overflow the context
window of the next call, the naive prune (drop the oldest N turns) loses
the high-signal turns that the model still needs (the original task
spec, the tool result that pinned a key fact). This pruner instead drops
the LOWEST-relevance turns subject to a strict token budget while
honoring three structural pins so the conversation never collapses
incoherently:

  1. The system prompt is ALWAYS kept (caller-tagged role="system").
  2. The most recent user turn is ALWAYS kept — pruning the prompt the
     model is about to answer is never the right call.
  3. Caller-pinned turns (`pinned=True`) are ALWAYS kept (e.g. a
     load-bearing tool result, a long-form spec, an answer the user has
     said "remember this").

Among the remaining turns, drop the ones with the LOWEST `relevance`
score first until the projected token total fits the budget. Ties are
broken by OLDER-first eviction (recency is a tiebreak signal, not the
primary signal — that's the whole point of this template).

Pure: no I/O, no clocks, no model calls. The relevance scorer is
INJECTED so the caller can use any signal — embedding cosine, recent-N
recency decay, an LLM rubric, a hand-built keyword filter.

Stdlib-only Python. Composes with `conversation-summarizer-window`
(summarize what was pruned into a single low-token "elided summary"
turn the caller can re-insert) and with `token-budget-tracker` (the
projected total after prune is the input to the next call's budget
ledger).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional


class PruneError(Exception):
    """Raised when prune is structurally impossible — e.g. the pinned
    turns alone already exceed the budget. Caller decides whether to
    fail loudly, climb to a bigger model, or summarize."""


@dataclass(frozen=True)
class Turn:
    turn_id: str
    role: str          # "system" | "user" | "assistant" | "tool"
    text: str
    tokens: int        # caller-supplied — use real tokenizer in prod
    pinned: bool = False


@dataclass(frozen=True)
class PruneResult:
    kept_ids: tuple[str, ...]            # in original order
    dropped_ids: tuple[str, ...]         # in eviction order (lowest relevance first)
    kept_tokens: int
    dropped_tokens: int
    budget_tokens: int
    pin_reasons: dict[str, str]          # turn_id -> "system" | "latest_user" | "explicit_pin"
    advice: str                          # "fits" | "tight" | "summarize_dropped"


def _validate(turns: list[Turn], budget_tokens: int) -> None:
    if budget_tokens <= 0:
        raise PruneError(f"budget_tokens must be > 0, got {budget_tokens}")
    seen: set[str] = set()
    for t in turns:
        if not isinstance(t, Turn):
            raise PruneError(f"non-Turn in input: {type(t).__name__}")
        if t.turn_id in seen:
            raise PruneError(f"duplicate turn_id: {t.turn_id}")
        seen.add(t.turn_id)
        if t.tokens < 0:
            raise PruneError(f"turn {t.turn_id} has negative tokens")
        if t.role not in ("system", "user", "assistant", "tool"):
            raise PruneError(f"turn {t.turn_id} has unknown role: {t.role}")


def prune(
    turns: list[Turn],
    budget_tokens: int,
    relevance_score: Callable[[Turn], float],
) -> PruneResult:
    """Prune `turns` so the kept-token total fits `budget_tokens`.

    `relevance_score(turn)` returns a float; HIGHER means more relevant
    and more likely to be kept. Pure function of one turn (caller can
    close over external state if needed)."""
    _validate(turns, budget_tokens)
    if not turns:
        return PruneResult(
            kept_ids=(),
            dropped_ids=(),
            kept_tokens=0,
            dropped_tokens=0,
            budget_tokens=budget_tokens,
            pin_reasons={},
            advice="fits",
        )

    # 1. determine pin set
    pin_reasons: dict[str, str] = {}
    latest_user_id: Optional[str] = None
    for t in turns:
        if t.role == "system":
            pin_reasons[t.turn_id] = "system"
        if t.pinned:
            # explicit_pin wins over system if both somehow apply
            pin_reasons.setdefault(t.turn_id, "explicit_pin")
            if t.role != "system":
                pin_reasons[t.turn_id] = "explicit_pin"
        if t.role == "user":
            latest_user_id = t.turn_id   # last one wins (most recent)
    if latest_user_id is not None:
        pin_reasons.setdefault(latest_user_id, "latest_user")

    # 2. compute pinned token cost; if it already exceeds the budget,
    # fail loudly. Silent over-budget would defeat the point.
    pinned_tokens = sum(t.tokens for t in turns if t.turn_id in pin_reasons)
    if pinned_tokens > budget_tokens:
        raise PruneError(
            f"pinned turns alone require {pinned_tokens} tokens, budget is {budget_tokens}"
        )

    # 3. score the prunable turns; build (relevance, original_index, turn) so
    # ties break by older-first (lower index = older = drop first).
    prunable: list[tuple[float, int, Turn]] = [
        (relevance_score(t), i, t)
        for i, t in enumerate(turns)
        if t.turn_id not in pin_reasons
    ]
    # eviction order: lowest relevance first; tie -> older first
    prunable.sort(key=lambda row: (row[0], row[1]))

    # 4. start with all turns kept; drop from the eviction list until fit.
    kept_ids_set: set[str] = {t.turn_id for t in turns}
    total_tokens = sum(t.tokens for t in turns)
    eviction_log: list[str] = []

    cursor = 0
    while total_tokens > budget_tokens and cursor < len(prunable):
        _, _, victim = prunable[cursor]
        kept_ids_set.discard(victim.turn_id)
        total_tokens -= victim.tokens
        eviction_log.append(victim.turn_id)
        cursor += 1

    if total_tokens > budget_tokens:
        # nothing left to prune but still over -- impossible because we
        # already checked pinned_tokens, but defend against future edits
        raise PruneError(
            f"could not prune to budget; {total_tokens} > {budget_tokens} after exhausting prunable turns"
        )

    kept_ids = tuple(t.turn_id for t in turns if t.turn_id in kept_ids_set)
    dropped_tokens = sum(t.tokens for t in turns if t.turn_id not in kept_ids_set)

    if eviction_log:
        advice = "summarize_dropped"
    elif total_tokens >= int(budget_tokens * 0.9):
        advice = "tight"
    else:
        advice = "fits"

    return PruneResult(
        kept_ids=kept_ids,
        dropped_ids=tuple(eviction_log),
        kept_tokens=total_tokens,
        dropped_tokens=dropped_tokens,
        budget_tokens=budget_tokens,
        pin_reasons=pin_reasons,
        advice=advice,
    )
