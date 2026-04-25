"""Pre-flight token + dollar estimate for a planned LLM call.

Pure, stdlib-only. The estimator does NOT issue the call. It returns a
structured estimate the orchestrator uses to decide whether to send,
downgrade the model, trim context, or refuse.

Token counting uses a deterministic byte-pair-ish heuristic so the
template is self-contained. Production deployments swap `count_tokens`
for the real tokenizer of their model family — the rest of the
estimator is unchanged.

Cost model is per-1k-tokens, separately for `prompt` and `completion`,
keyed by model id. Unknown models raise — silent fallback to "free" is
the wrong default for a budget gate.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict
from typing import Iterable


# --- token counter ---------------------------------------------------------

# Heuristic: word-ish runs + punctuation, then ~4-char-per-token compression
# for long alpha runs. Calibrates to within ~10% of cl100k_base for English
# prose; production callers replace this with a real tokenizer.
_WORD_RE = re.compile(r"\w+|[^\s\w]", re.UNICODE)


def count_tokens(text: str) -> int:
    if not text:
        return 0
    n = 0
    for tok in _WORD_RE.findall(text):
        # short tokens cost 1; longer alpha runs split roughly per 4 chars
        if len(tok) <= 4:
            n += 1
        else:
            n += (len(tok) + 3) // 4
    return n


# --- pricing ---------------------------------------------------------------

@dataclass(frozen=True)
class ModelPrice:
    """USD per 1000 tokens, separately for input and output."""
    prompt_per_1k: float
    completion_per_1k: float


# Static pricing table. Real deployments load this from a file pinned in
# git so a price change is a reviewable diff.
DEFAULT_PRICES: dict[str, ModelPrice] = {
    "small-fast":   ModelPrice(prompt_per_1k=0.00015, completion_per_1k=0.00060),
    "mid-balanced": ModelPrice(prompt_per_1k=0.00250, completion_per_1k=0.01000),
    "big-smart":    ModelPrice(prompt_per_1k=0.01500, completion_per_1k=0.06000),
}


# --- estimate --------------------------------------------------------------

@dataclass
class CallPlan:
    """What the caller intends to send."""
    model: str
    system_prompt: str = ""
    user_prompt: str = ""
    # extra prompt-side material: retrieved docs, tool schemas, prior turns
    extras: list[str] = field(default_factory=list)
    # caller's own ceiling on completion length, in tokens
    max_completion_tokens: int = 512


@dataclass
class Estimate:
    model: str
    prompt_tokens: int
    completion_tokens_max: int
    total_tokens_max: int
    prompt_cost_usd: float
    completion_cost_usd_max: float
    total_cost_usd_max: float
    # what fraction of the model's nominal context window the prompt fills
    context_fill_ratio: float

    def to_dict(self) -> dict:
        return asdict(self)


# Nominal context window per model (tokens). Used only for the fill ratio.
DEFAULT_CONTEXT_WINDOWS: dict[str, int] = {
    "small-fast":   8_192,
    "mid-balanced": 32_768,
    "big-smart":    128_000,
}


class UnknownModel(KeyError):
    pass


def estimate(
    plan: CallPlan,
    prices: dict[str, ModelPrice] | None = None,
    context_windows: dict[str, int] | None = None,
) -> Estimate:
    prices = prices if prices is not None else DEFAULT_PRICES
    ctx_windows = context_windows if context_windows is not None else DEFAULT_CONTEXT_WINDOWS

    if plan.model not in prices:
        raise UnknownModel(plan.model)

    price = prices[plan.model]
    ctx = ctx_windows.get(plan.model, 0)

    prompt_tokens = (
        count_tokens(plan.system_prompt)
        + count_tokens(plan.user_prompt)
        + sum(count_tokens(x) for x in plan.extras)
    )
    completion_tokens_max = max(0, plan.max_completion_tokens)
    total_tokens_max = prompt_tokens + completion_tokens_max

    prompt_cost = prompt_tokens / 1000.0 * price.prompt_per_1k
    completion_cost_max = completion_tokens_max / 1000.0 * price.completion_per_1k
    total_cost_max = prompt_cost + completion_cost_max

    fill = (prompt_tokens / ctx) if ctx > 0 else 0.0

    return Estimate(
        model=plan.model,
        prompt_tokens=prompt_tokens,
        completion_tokens_max=completion_tokens_max,
        total_tokens_max=total_tokens_max,
        prompt_cost_usd=round(prompt_cost, 6),
        completion_cost_usd_max=round(completion_cost_max, 6),
        total_cost_usd_max=round(total_cost_max, 6),
        context_fill_ratio=round(fill, 4),
    )


# --- gate ------------------------------------------------------------------

@dataclass
class GateDecision:
    allow: bool
    reason: str
    estimate: Estimate


def gate(
    plan: CallPlan,
    *,
    max_cost_usd: float,
    max_context_fill: float = 0.90,
    prices: dict[str, ModelPrice] | None = None,
    context_windows: dict[str, int] | None = None,
) -> GateDecision:
    """Pre-flight allow/deny against an explicit per-call budget."""
    est = estimate(plan, prices=prices, context_windows=context_windows)
    if est.total_cost_usd_max > max_cost_usd:
        return GateDecision(
            allow=False,
            reason=f"cost ceiling exceeded: ${est.total_cost_usd_max:.4f} > ${max_cost_usd:.4f}",
            estimate=est,
        )
    if est.context_fill_ratio > max_context_fill:
        return GateDecision(
            allow=False,
            reason=f"context fill exceeded: {est.context_fill_ratio:.2%} > {max_context_fill:.0%}",
            estimate=est,
        )
    return GateDecision(allow=True, reason="ok", estimate=est)


def cheapest_model_that_fits(
    plan: CallPlan,
    candidates: Iterable[str],
    *,
    max_cost_usd: float,
    max_context_fill: float = 0.90,
    prices: dict[str, ModelPrice] | None = None,
    context_windows: dict[str, int] | None = None,
) -> tuple[str, Estimate] | None:
    """Pick the cheapest model from `candidates` whose estimate fits both gates.

    Returns (model_id, estimate) or None if nothing fits.
    """
    prices = prices if prices is not None else DEFAULT_PRICES
    fits: list[tuple[str, Estimate]] = []
    for m in candidates:
        p = CallPlan(
            model=m,
            system_prompt=plan.system_prompt,
            user_prompt=plan.user_prompt,
            extras=list(plan.extras),
            max_completion_tokens=plan.max_completion_tokens,
        )
        d = gate(
            p,
            max_cost_usd=max_cost_usd,
            max_context_fill=max_context_fill,
            prices=prices,
            context_windows=context_windows,
        )
        if d.allow:
            fits.append((m, d.estimate))
    if not fits:
        return None
    fits.sort(key=lambda x: x[1].total_cost_usd_max)
    return fits[0]
