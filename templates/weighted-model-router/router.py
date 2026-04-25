"""Weighted, deterministic model router.

Routes a request to one of N candidate model backends based on
caller-declared weights, with two correctness guarantees that the
naive "random.choices" implementation gets wrong:

1. **Deterministic given a route_key.** Same `route_key` always lands
   on the same backend regardless of process restart, host, or
   `random.seed` state. This is what makes "pin user X to model A
   for the duration of an A/B" actually work, and what makes a
   replayed trace land on the same model as the original.

2. **Stable under weight edits that touch unrelated buckets.** Adding
   a brand-new backend at weight=5 should reroute roughly 5/(5+old_total)
   of traffic, not reshuffle every existing key. This template uses
   rendezvous (HRW) hashing precisely so an unrelated weight tweak
   does not invalidate the cache / sticky-session assumptions of
   keys that were not in the affected bucket.

Excluded backends (drained / circuit-open) are filtered *before*
selection so a drained backend can never win even with a high weight,
and `route` raises `NoEligibleBackend` if every candidate is excluded
rather than silently degrading to a random pick.

Stdlib-only. No I/O, no clocks. Caller composes with their own
health-check / circuit-breaker / cost-budget logic.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field
from typing import Iterable


class NoEligibleBackend(Exception):
    """Raised when every candidate backend is excluded."""


class InvalidWeight(Exception):
    """Raised when a backend's weight is <= 0 or non-finite."""


@dataclass(frozen=True)
class Backend:
    name: str
    weight: float

    def __post_init__(self) -> None:
        if not math.isfinite(self.weight) or self.weight <= 0:
            raise InvalidWeight(
                f"backend {self.name!r}: weight must be finite and > 0, got {self.weight!r}"
            )


@dataclass
class RouteResult:
    backend: str
    score: float
    considered: int
    excluded: tuple[str, ...]


@dataclass
class WeightedRouter:
    """Rendezvous-hashing weighted router.

    Selection rule: for each candidate backend `b`, compute
        score(b) = b.weight / -ln(uniform_hash(route_key, b.name))
    and pick the backend with the maximum score. This is the standard
    weighted-rendezvous (HRW) construction (Schindler 2005); weight
    edits to one bucket only affect the keys whose top-2 scoring
    backends straddled that bucket.
    """

    backends: tuple[Backend, ...]

    def __post_init__(self) -> None:
        seen: set[str] = set()
        for b in self.backends:
            if b.name in seen:
                raise InvalidWeight(f"duplicate backend name: {b.name!r}")
            seen.add(b.name)
        if not self.backends:
            raise InvalidWeight("router needs at least one backend")

    def route(
        self,
        route_key: str,
        *,
        exclude: Iterable[str] = (),
    ) -> RouteResult:
        excluded_set = frozenset(exclude)
        candidates = [b for b in self.backends if b.name not in excluded_set]
        if not candidates:
            raise NoEligibleBackend(
                f"all {len(self.backends)} backends excluded for key {route_key!r}"
            )
        best: tuple[float, str] | None = None
        for b in candidates:
            u = _uniform_hash(route_key, b.name)
            # score = weight / -ln(u); higher weight → larger score on average.
            score = b.weight / -math.log(u)
            if best is None or score > best[0]:
                best = (score, b.name)
            elif score == best[0] and b.name < best[1]:
                # Deterministic tiebreak by lexicographic name.
                best = (score, b.name)
        assert best is not None
        return RouteResult(
            backend=best[1],
            score=best[0],
            considered=len(candidates),
            excluded=tuple(sorted(excluded_set)),
        )


def _uniform_hash(route_key: str, backend_name: str) -> float:
    """Map (route_key, backend_name) → float in (0, 1)."""
    h = hashlib.blake2b(
        f"{route_key}\x00{backend_name}".encode("utf-8"), digest_size=8
    ).digest()
    n = int.from_bytes(h, "big")
    # Avoid 0 (would make -ln(0) = +inf and break tiebreak determinism).
    # 2**64 - 1 max; map to (0, 1] then strictly < 1.
    u = (n + 1) / (1 << 64)
    if u >= 1.0:
        u = 1.0 - 2**-53
    return u
