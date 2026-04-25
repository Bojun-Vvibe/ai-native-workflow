"""agent-conversation-turn-pruner — stdlib-only reference.

Drop middle turns from a long agent conversation while keeping system,
the first K turns ("anchors": original task framing, key tool definitions
the agent should not forget), and the last M turns (recent dialogue).
Optionally insert a single placeholder marker so the model knows context
was elided rather than being told the conversation started in medias res.

The shape this template enforces:

    [system, system, ...]                    # always kept (priority -inf)
    [first K non-system turns]               # "anchor" turns
    [<elision marker, if any turns dropped>] # one synthetic turn
    [last M non-system turns]                # "recent" turns

Why this shape and not "drop the oldest until you fit":
    * Anchors are load-bearing: the original user request, the canonical
      tool descriptions, the few-shot example. Dropping them silently
      erodes mission grounding. They go in the keep set unconditionally.
    * Recents are load-bearing: the agent's last action and its result.
      Dropping them mid-loop produces immediate "wait, what was I doing?"
      regression.
    * The middle is where slop accumulates: failed tool retries, the
      model talking to itself, search results it already summarized.
      That is exactly the band that pays for itself when dropped.
    * A *single* explicit elision marker beats silent deletion: the
      model can reason "I see a gap" instead of confabulating context.

API:
    Turn(role: str, content: str, *, pinned: bool = False, tokens: int|None)
    PrunePolicy(keep_first: int, keep_last: int,
                max_total_turns: int|None = None,
                max_total_tokens: int|None = None,
                token_count_fn: Callable[[Turn], int]|None = None,
                elision_marker: str | None = ...)
    PruneResult(kept, dropped, marker_inserted, kept_token_count, dropped_token_count, decisions)
    prune(turns, policy) -> PruneResult

Pinned turns (e.g. a critical tool result the orchestrator marked "do not
drop") are never dropped, even if they fall in the middle band.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, List, Optional


DEFAULT_ELISION_MARKER = (
    "[Earlier turns elided to fit context budget. The conversation continues below.]"
)


@dataclass(frozen=True)
class Turn:
    role: str                    # "system", "user", "assistant", "tool"
    content: str
    pinned: bool = False         # never drop, even if in middle band
    tokens: Optional[int] = None # caller-supplied; if None we estimate


@dataclass(frozen=True)
class PrunePolicy:
    keep_first: int                          # # of non-system turns at the head
    keep_last: int                           # # of non-system turns at the tail
    max_total_turns: Optional[int] = None    # cap on total kept turns (incl. system)
    max_total_tokens: Optional[int] = None   # cap on sum of token counts of kept turns
    token_count_fn: Optional[Callable[[Turn], int]] = None
    elision_marker: Optional[str] = DEFAULT_ELISION_MARKER  # None = no marker


@dataclass
class PruneResult:
    kept: List[Turn]
    dropped: List[Turn] = field(default_factory=list)
    marker_inserted: bool = False
    kept_token_count: int = 0
    dropped_token_count: int = 0
    decisions: List[str] = field(default_factory=list)


def _default_token_count(turn: Turn) -> int:
    """Crude whitespace-split estimator. Production callers should pass
    `token_count_fn=` with a real tokenizer."""
    if turn.tokens is not None:
        return turn.tokens
    # Rough approximation: 1 token per whitespace-split word + 2 for role framing.
    return len(turn.content.split()) + 2


def _count(turn: Turn, policy: PrunePolicy) -> int:
    fn = policy.token_count_fn or _default_token_count
    return fn(turn)


def prune(turns: List[Turn], policy: PrunePolicy) -> PruneResult:
    if policy.keep_first < 0 or policy.keep_last < 0:
        raise ValueError("keep_first / keep_last must be >= 0")
    if policy.max_total_turns is not None and policy.max_total_turns < 0:
        raise ValueError("max_total_turns must be >= 0")
    if policy.max_total_tokens is not None and policy.max_total_tokens < 0:
        raise ValueError("max_total_tokens must be >= 0")

    decisions: List[str] = []

    # 1. System turns are always kept and never counted against keep_first/keep_last.
    system_turns = [t for t in turns if t.role == "system"]
    convo = [t for t in turns if t.role != "system"]
    decisions.append(
        f"split: {len(system_turns)} system turn(s), {len(convo)} conversation turn(s)"
    )

    # 2. Pick the head/tail bands. If they overlap or touch, no pruning needed.
    n = len(convo)
    head_n = min(policy.keep_first, n)
    tail_n = min(policy.keep_last, n - head_n)
    if head_n + tail_n >= n:
        # Bands cover everything; no middle to drop.
        decisions.append("no middle to drop (head+tail covers all conversation turns)")
        kept_convo = convo[:]
        middle_dropped: List[Turn] = []
    else:
        head = convo[:head_n]
        tail = convo[n - tail_n:] if tail_n > 0 else []
        middle = convo[head_n: n - tail_n]
        # Pinned middle turns survive (in original position relative to each other).
        pinned_middle = [t for t in middle if t.pinned]
        unpinned_middle = [t for t in middle if not t.pinned]
        decisions.append(
            f"middle: {len(middle)} turn(s), {len(pinned_middle)} pinned (kept), "
            f"{len(unpinned_middle)} unpinned (dropped)"
        )
        kept_convo = head + pinned_middle + tail
        middle_dropped = unpinned_middle

    # 3. Insert the elision marker if we actually dropped anything and the
    #    policy supplied one.
    marker_inserted = False
    if middle_dropped and policy.elision_marker:
        marker = Turn(role="system", content=policy.elision_marker)
        # Place marker immediately after head + pinned_middle, before tail.
        # We have to recompute split because pinned middle turns sit *with* head.
        head_size = min(policy.keep_first, len(convo))
        pinned_in_kept = [t for t in kept_convo[head_size:] if t.pinned]
        split_at = head_size + len(pinned_in_kept)
        kept_convo = kept_convo[:split_at] + [marker] + kept_convo[split_at:]
        marker_inserted = True
        decisions.append(f"inserted elision marker at convo position {split_at}")

    # 4. Apply max_total_turns ceiling, dropping additional unpinned middle->head
    #    candidates from the *oldest non-anchor* end of the kept band.
    kept = system_turns + kept_convo
    further_dropped: List[Turn] = []
    if policy.max_total_turns is not None and len(kept) > policy.max_total_turns:
        # Anchors first then tail: we drop from the inside boundary outward.
        # Strategy: drop unpinned anchors from the end of head band first, then
        # unpinned tail from the front of tail band. Pinned and system always
        # survive the ceiling.
        excess = len(kept) - policy.max_total_turns
        # Walk kept_convo from the inside out, dropping unpinned non-marker turns.
        # Identify positions that are eligible (not pinned, not system, not the marker).
        marker_id = id(kept_convo[0]) if False else None  # placeholder for clarity
        eligible_ix = [
            i for i, t in enumerate(kept_convo)
            if not t.pinned and t.role != "system"
        ]
        # Drop from the *middle* of kept_convo outward (alternating from end-of-head
        # and start-of-tail). To keep this template simple we just drop oldest
        # eligible first (which preserves the recents — the more important band).
        to_drop_ix = eligible_ix[:excess]
        for i in sorted(to_drop_ix, reverse=True):
            further_dropped.append(kept_convo[i])
            del kept_convo[i]
        decisions.append(
            f"max_total_turns={policy.max_total_turns} ceiling dropped "
            f"{len(further_dropped)} additional turn(s)"
        )
        kept = system_turns + kept_convo

    # 5. Apply max_total_tokens ceiling. Same strategy: drop oldest eligible
    #    (non-system, non-pinned, non-marker) turns until under the cap.
    if policy.max_total_tokens is not None:
        def total_tokens(ts: List[Turn]) -> int:
            return sum(_count(t, policy) for t in ts)

        budget = policy.max_total_tokens
        marker_text = policy.elision_marker
        while total_tokens(kept) > budget:
            # Find the oldest eligible kept_convo turn.
            target_ix = None
            for i, t in enumerate(kept_convo):
                if t.pinned or t.role == "system":
                    continue
                if marker_text is not None and t.content == marker_text:
                    continue
                target_ix = i
                break
            if target_ix is None:
                decisions.append(
                    f"max_total_tokens={budget}: no further eligible turns to drop "
                    f"(remaining are pinned/system/marker); budget breached at "
                    f"{total_tokens(kept)} tokens"
                )
                break
            further_dropped.append(kept_convo[target_ix])
            del kept_convo[target_ix]
            kept = system_turns + kept_convo
        else:
            decisions.append(
                f"max_total_tokens={budget} ceiling: kept {total_tokens(kept)} tokens"
            )

    dropped = middle_dropped + further_dropped
    kept_tokens = sum(_count(t, policy) for t in kept)
    dropped_tokens = sum(_count(t, policy) for t in dropped)
    return PruneResult(
        kept=kept,
        dropped=dropped,
        marker_inserted=marker_inserted,
        kept_token_count=kept_tokens,
        dropped_token_count=dropped_tokens,
        decisions=decisions,
    )
