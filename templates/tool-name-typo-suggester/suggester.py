"""Pure stdlib tool-name typo detector + suggester.

Given a registry of known tool names and the (possibly misspelled) name an
agent just emitted, return one of three verdicts:

    - exact:        the name is in the registry verbatim
    - suggestion:   not in the registry, but a single best candidate is
                    within `max_distance` AND beats the second-best by at
                    least `tie_break_margin` characters
    - unknown:      no candidate within `max_distance`, OR two candidates
                    are tied within `tie_break_margin` (ambiguous; surface
                    both rather than guess wrong)

The point: when an agent emits `read_fil` instead of `read_file`, the host
should NOT respond with "tool not found" (the agent will just retry the
same typo). It should respond with a structured suggestion the agent's
next turn can act on, OR — under explicit policy — auto-correct.

Distance is Damerau-Levenshtein with a transposition rule, on the
case-folded-and-normalized name (alnum + underscore only). This catches
the four typo classes that actually happen in agent output: single-char
substitution (`read_fle` -> `read_file`), single-char insertion
(`read_files` -> `read_file`), single-char deletion (`read_fil` ->
`read_file`), and adjacent transposition (`raed_file` -> `read_file`).

Stdlib only. No fuzz library, no embeddings. Deterministic.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable


_NORMALIZE_RE = re.compile(r"[^a-z0-9_]")


def _normalize(name: str) -> str:
    return _NORMALIZE_RE.sub("", name.lower())


def _damerau_levenshtein(a: str, b: str) -> int:
    """Optimal-string-alignment / Damerau-Levenshtein distance.

    Counts adjacent transposition as cost 1 (so `raed` -> `read` is 1, not 2).
    Pure dynamic programming, no external deps.
    """
    if a == b:
        return 0
    la, lb = len(a), len(b)
    if la == 0:
        return lb
    if lb == 0:
        return la
    # Rows: la+1, cols: lb+1.
    prev2 = [0] * (lb + 1)
    prev1 = list(range(lb + 1))
    curr = [0] * (lb + 1)
    for i in range(1, la + 1):
        curr[0] = i
        for j in range(1, lb + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            curr[j] = min(
                curr[j - 1] + 1,        # insertion
                prev1[j] + 1,           # deletion
                prev1[j - 1] + cost,    # substitution
            )
            if (
                i >= 2
                and j >= 2
                and a[i - 1] == b[j - 2]
                and a[i - 2] == b[j - 1]
            ):
                curr[j] = min(curr[j], prev2[j - 2] + 1)
        prev2, prev1, curr = prev1, curr, prev2
    return prev1[lb]


@dataclass(frozen=True)
class Suggestion:
    """Result of suggesting against the registry.

    verdict: "exact" | "suggestion" | "unknown"
    best:        winning candidate (exact match or top suggestion); None for unknown
    distance:    edit distance from input to `best`; 0 for exact, None for unknown
    runners_up:  list of (name, distance) for the next-best candidates within
                 max_distance, in distance-then-alphabetical order. Useful when
                 verdict="unknown" because two candidates tied — the orchestrator
                 can show both to the agent.
    reason:      stable enum string for logging:
                 "exact_match" | "single_candidate" | "clear_winner" |
                 "ambiguous" | "no_candidate_within_distance" | "empty_registry"
    """
    verdict: str
    best: str | None
    distance: int | None
    runners_up: list[tuple[str, int]]
    reason: str


class TypoSuggester:
    """Stable, registry-backed typo suggester.

    Construction validates the registry (rejects empty names, duplicates after
    normalization) so the gate cannot silently degrade because two tools
    `read_file` and `read-file` collapse onto the same key.
    """

    def __init__(
        self,
        registry: Iterable[str],
        *,
        max_distance: int = 2,
        tie_break_margin: int = 1,
    ) -> None:
        if max_distance < 1:
            raise ValueError("max_distance must be >= 1")
        if tie_break_margin < 0:
            raise ValueError("tie_break_margin must be >= 0")
        # Preserve original spelling per normalized key; reject collisions.
        seen: dict[str, str] = {}
        for raw in registry:
            if not isinstance(raw, str) or not raw:
                raise ValueError(f"registry entries must be non-empty strings: {raw!r}")
            norm = _normalize(raw)
            if not norm:
                raise ValueError(f"registry entry normalized to empty: {raw!r}")
            if norm in seen and seen[norm] != raw:
                raise ValueError(
                    f"registry collision after normalization: {seen[norm]!r} vs {raw!r}"
                )
            seen[norm] = raw
        self._registry: dict[str, str] = seen  # norm -> original
        self._max_distance = max_distance
        self._tie_break_margin = tie_break_margin

    @property
    def known_names(self) -> list[str]:
        return sorted(self._registry.values())

    def suggest(self, name: str) -> Suggestion:
        if not self._registry:
            return Suggestion("unknown", None, None, [], "empty_registry")
        if not isinstance(name, str) or not name:
            return Suggestion("unknown", None, None, [], "no_candidate_within_distance")
        norm = _normalize(name)
        if norm in self._registry:
            return Suggestion(
                "exact", self._registry[norm], 0, [], "exact_match"
            )
        # Compute distances to every candidate.
        scored: list[tuple[str, int]] = []
        for cand_norm, cand_orig in self._registry.items():
            d = _damerau_levenshtein(norm, cand_norm)
            if d <= self._max_distance:
                scored.append((cand_orig, d))
        if not scored:
            return Suggestion(
                "unknown", None, None, [], "no_candidate_within_distance"
            )
        # Sort by distance asc, then alphabetical for stability.
        scored.sort(key=lambda x: (x[1], x[0]))
        best_name, best_dist = scored[0]
        if len(scored) == 1:
            return Suggestion(
                "suggestion", best_name, best_dist, [], "single_candidate"
            )
        runner_name, runner_dist = scored[1]
        if runner_dist - best_dist >= self._tie_break_margin and self._tie_break_margin > 0:
            return Suggestion(
                "suggestion",
                best_name,
                best_dist,
                scored[1:],
                "clear_winner",
            )
        # Ambiguous: distances too close. Surface all near-ties so the agent
        # picks rather than guess wrong.
        return Suggestion(
            "unknown",
            None,
            None,
            scored,
            "ambiguous",
        )
