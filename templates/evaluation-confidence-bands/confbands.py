"""Evaluation confidence bands.

Turn a list of per-item LLM eval scores (each in [0, 1]) into a
mean with bootstrap confidence-interval (CI) bands. When two
candidates' CIs overlap by more than a tunable margin, refuse to
rank — the data does not justify a winner.

Stdlib only. Deterministic: bootstrap resampling uses an injected
`random.Random` (seeded), not the global RNG.

Public API
----------
- bootstrap_ci(scores, *, rng, iters, alpha) -> CIBand
- compare(a_band, b_band, *, overlap_margin) -> Comparison
- format_band(band) -> str
- format_comparison(cmp) -> str

Notes on the statistics
-----------------------
This is a percentile bootstrap, not a BCa bootstrap. It's correct
enough for "should I trust this ranking?" decisions and has zero
external deps. For publication-grade intervals reach for SciPy.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Sequence


@dataclass(frozen=True)
class CIBand:
    name: str
    n: int
    mean: float
    lower: float
    upper: float
    alpha: float
    iters: int


@dataclass(frozen=True)
class Comparison:
    a: str
    b: str
    a_mean: float
    b_mean: float
    overlap: float           # signed gap in CI space; >0 => overlapping
    overlap_margin: float
    decision: str            # "a_wins" | "b_wins" | "refuse"
    reason: str


def _validate_scores(scores: Sequence[float]) -> None:
    if not scores:
        raise ValueError("scores must be non-empty")
    for s in scores:
        if not isinstance(s, (int, float)):
            raise TypeError(f"score must be numeric, got {type(s).__name__}")
        if not 0.0 <= float(s) <= 1.0:
            raise ValueError(f"score {s} outside [0,1]")


def bootstrap_ci(
    scores: Sequence[float],
    *,
    name: str,
    rng: random.Random,
    iters: int = 2000,
    alpha: float = 0.05,
) -> CIBand:
    """Percentile bootstrap CI for the mean.

    `rng` is required and must be a seeded `random.Random` so the
    output is reproducible. We never touch the global RNG.
    """
    _validate_scores(scores)
    if iters < 100:
        raise ValueError("iters must be >= 100 for a meaningful CI")
    if not 0.0 < alpha < 1.0:
        raise ValueError("alpha must be in (0, 1)")

    n = len(scores)
    means: list[float] = []
    for _ in range(iters):
        sample = [scores[rng.randrange(n)] for _ in range(n)]
        means.append(sum(sample) / n)
    means.sort()

    lo_idx = max(0, int((alpha / 2.0) * iters))
    hi_idx = min(iters - 1, int((1.0 - alpha / 2.0) * iters))

    return CIBand(
        name=name,
        n=n,
        mean=sum(scores) / n,
        lower=means[lo_idx],
        upper=means[hi_idx],
        alpha=alpha,
        iters=iters,
    )


def compare(
    a: CIBand,
    b: CIBand,
    *,
    overlap_margin: float = 0.0,
) -> Comparison:
    """Decide whether a and b can be ranked.

    `overlap_margin` is in score units. The CIs are considered
    "effectively overlapping" if `min(a.upper, b.upper) -
    max(a.lower, b.lower) > -overlap_margin`. With margin=0 we
    require strict CI separation; with margin=0.02 we tolerate up
    to 2 score-points of overlap before refusing.
    """
    if overlap_margin < 0.0:
        raise ValueError("overlap_margin must be >= 0")

    overlap = min(a.upper, b.upper) - max(a.lower, b.lower)
    overlapping = overlap > -overlap_margin

    if overlapping:
        decision = "refuse"
        reason = (
            f"CIs overlap by {overlap:+.4f} (margin={overlap_margin});"
            " ranking is not justified by the data"
        )
    elif a.mean > b.mean:
        decision = "a_wins"
        reason = (
            f"a CI [{a.lower:.4f},{a.upper:.4f}] is strictly above "
            f"b CI [{b.lower:.4f},{b.upper:.4f}]"
        )
    else:
        decision = "b_wins"
        reason = (
            f"b CI [{b.lower:.4f},{b.upper:.4f}] is strictly above "
            f"a CI [{a.lower:.4f},{a.upper:.4f}]"
        )

    return Comparison(
        a=a.name,
        b=b.name,
        a_mean=a.mean,
        b_mean=b.mean,
        overlap=overlap,
        overlap_margin=overlap_margin,
        decision=decision,
        reason=reason,
    )


def format_band(band: CIBand) -> str:
    pct = int((1.0 - band.alpha) * 100)
    return (
        f"{band.name}: n={band.n} mean={band.mean:.4f} "
        f"{pct}%CI=[{band.lower:.4f}, {band.upper:.4f}] "
        f"(iters={band.iters})"
    )


def format_comparison(cmp: Comparison) -> str:
    return (
        f"compare({cmp.a!r} vs {cmp.b!r}): "
        f"means={cmp.a_mean:.4f}/{cmp.b_mean:.4f} "
        f"overlap={cmp.overlap:+.4f} "
        f"margin={cmp.overlap_margin} -> {cmp.decision}\n"
        f"  reason: {cmp.reason}"
    )
