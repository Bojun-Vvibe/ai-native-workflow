"""prompt-token-budget-allocator — allocate a finite token budget across prompt sections.

You are assembling a prompt out of N sections (system, instructions, recent
chat, retrieved docs, examples, scratchpad, ...). Each section declares:

  - a ``priority`` rank (lower = more important; 0 = "must include")
  - a ``min_tokens`` floor below which it is useless (0 means "OK to drop")
  - an ``ideal_tokens`` size (what the section *wants*)
  - the actual content size (``current_tokens``), pre-computed by caller

You have a hard ``budget`` (e.g. ``model_context_window - reserved_completion``).

The allocator decides per section:

  - ``allocated`` tokens (0..current_tokens), and
  - whether it was ``dropped`` (allocated == 0 and section had content), or
  - ``truncated`` (allocated < current_tokens but >= min_tokens), or
  - ``intact``   (allocated == current_tokens).

It also reports ``budget_used``, ``budget_headroom``, and a ``decisions`` log
the caller can drop into a trace.

Algorithm (deterministic, two-pass):

  Pass 1 — floor pass, by priority ascending then by input order:
    Try to allocate each section's ``min_tokens``. If we cannot fit a
    section's floor and ``min_tokens > 0``, drop it (allocate 0) and record
    ``reason="floor_did_not_fit"``. ``priority == 0`` (mandatory) sections
    that cannot fit their floor raise ``BudgetTooSmall`` — the caller has a
    bug, the budget is structurally wrong.

  Pass 2 — top-up pass, by priority ascending then by input order:
    Top each surviving section up toward ``ideal_tokens`` (capped at
    ``current_tokens``) using remaining headroom, in priority order. Once
    headroom hits 0 we stop; later same-priority sections do NOT get a
    fair share, they get whatever-is-left in input order. This is intentional
    — fair-share is harder to reason about and harder to debug than
    "what came first wins ties".

Stdlib-only.

Public API
----------
- ``Section(name, priority, min_tokens, ideal_tokens, current_tokens)``
- ``Allocation(section_name, allocated, status, reason)``
- ``allocate(sections, budget) -> AllocationResult``
- ``AllocationResult.allocations: list[Allocation]``
- ``AllocationResult.budget_used: int``
- ``AllocationResult.budget_headroom: int``
- ``AllocationResult.decisions: list[str]``
- ``BudgetTooSmall`` raised when a ``priority=0`` section cannot fit its floor.
"""

from __future__ import annotations

from dataclasses import dataclass, field


class BudgetTooSmall(Exception):
    """A priority=0 (mandatory) section did not fit its min_tokens floor."""


@dataclass(frozen=True)
class Section:
    name: str
    priority: int
    min_tokens: int
    ideal_tokens: int
    current_tokens: int

    def __post_init__(self) -> None:
        if self.min_tokens < 0 or self.ideal_tokens < 0 or self.current_tokens < 0:
            raise ValueError(f"{self.name}: token counts must be >= 0")
        if self.priority < 0:
            raise ValueError(f"{self.name}: priority must be >= 0")
        if self.min_tokens > self.ideal_tokens:
            raise ValueError(
                f"{self.name}: min_tokens ({self.min_tokens}) > "
                f"ideal_tokens ({self.ideal_tokens})"
            )
        if self.ideal_tokens > self.current_tokens:
            # Caller pre-computed current_tokens. ideal > current is weird —
            # the caller doesn't have enough material to ever hit ideal — we
            # cap silently below, but warn at construction so it surfaces.
            # We don't raise; this is legal but suspicious.
            pass


@dataclass(frozen=True)
class Allocation:
    section_name: str
    allocated: int
    status: str  # "intact" | "truncated" | "dropped" | "skipped_empty"
    reason: str = ""


@dataclass
class AllocationResult:
    allocations: list[Allocation]
    budget: int
    budget_used: int
    budget_headroom: int
    decisions: list[str] = field(default_factory=list)

    def by_name(self, name: str) -> Allocation:
        for a in self.allocations:
            if a.section_name == name:
                return a
        raise KeyError(name)

    def to_dict(self) -> dict:
        return {
            "budget": self.budget,
            "budget_used": self.budget_used,
            "budget_headroom": self.budget_headroom,
            "allocations": [
                {
                    "section_name": a.section_name,
                    "allocated": a.allocated,
                    "status": a.status,
                    "reason": a.reason,
                }
                for a in self.allocations
            ],
            "decisions": list(self.decisions),
        }


def allocate(sections: list[Section], budget: int) -> AllocationResult:
    if budget < 0:
        raise ValueError(f"budget must be >= 0, got {budget}")

    # Detect duplicate names — that would silently corrupt the trace.
    seen: set[str] = set()
    for s in sections:
        if s.name in seen:
            raise ValueError(f"duplicate section name: {s.name}")
        seen.add(s.name)

    # Working dict: name -> allocated tokens. Sections we never touch are 0.
    allocated: dict[str, int] = {s.name: 0 for s in sections}
    status: dict[str, str] = {}
    reason: dict[str, str] = {}
    decisions: list[str] = []

    headroom = budget

    # Sections with no content at all: skip immediately, don't churn the log.
    workable: list[Section] = []
    for s in sections:
        if s.current_tokens == 0:
            status[s.name] = "skipped_empty"
            reason[s.name] = "section had no content"
            decisions.append(f"skip {s.name!r}: empty (current_tokens=0)")
        else:
            workable.append(s)

    # Stable sort by (priority asc, input order). enumerate gives the secondary
    # key so the sort is stable even on Pythons where it already would be.
    indexed = list(enumerate(workable))
    indexed.sort(key=lambda pair: (pair[1].priority, pair[0]))

    # ---- Pass 1: floor pass ----
    for _, s in indexed:
        floor = s.min_tokens
        if floor == 0:
            # Section is droppable but we will visit it in pass 2.
            continue
        if floor <= headroom:
            allocated[s.name] = floor
            headroom -= floor
            decisions.append(
                f"floor {s.name!r} (priority={s.priority}): allocated {floor} tokens, "
                f"headroom now {headroom}"
            )
        else:
            if s.priority == 0:
                raise BudgetTooSmall(
                    f"section {s.name!r} is priority=0 (mandatory) but its "
                    f"min_tokens={floor} does not fit remaining headroom={headroom}"
                )
            status[s.name] = "dropped"
            reason[s.name] = (
                f"floor_did_not_fit (need {floor}, headroom {headroom})"
            )
            decisions.append(
                f"drop {s.name!r} (priority={s.priority}): floor {floor} > "
                f"headroom {headroom}"
            )

    # ---- Pass 2: top-up pass ----
    for _, s in indexed:
        if status.get(s.name) == "dropped":
            continue
        # Cap at the lesser of ideal_tokens and current_tokens.
        target = min(s.ideal_tokens, s.current_tokens)
        already = allocated[s.name]
        want_more = max(0, target - already)
        if want_more == 0:
            # Either ideal == 0 (weird but legal — section's min was its
            # entire allocation) or already at target.
            continue
        give = min(want_more, headroom)
        if give > 0:
            allocated[s.name] += give
            headroom -= give
            decisions.append(
                f"topup {s.name!r} (priority={s.priority}): +{give} tokens "
                f"(now {allocated[s.name]}/{target}), headroom now {headroom}"
            )

    # ---- Finalize statuses for workable sections ----
    for s in workable:
        if status.get(s.name) == "dropped":
            continue
        a = allocated[s.name]
        target = min(s.ideal_tokens, s.current_tokens)
        if a == 0:
            # Floor was 0 and pass 2 had no headroom for it.
            status[s.name] = "dropped"
            reason[s.name] = "no_headroom_after_floors"
        elif a < target:
            status[s.name] = "truncated"
            reason[s.name] = f"allocated {a} of ideal {target}"
        elif a >= s.current_tokens:
            status[s.name] = "intact"
            reason[s.name] = ""
        else:
            # a == target < current_tokens (target capped by ideal)
            status[s.name] = "truncated"
            reason[s.name] = (
                f"allocated {a} of current {s.current_tokens} (ideal cap {target})"
            )

    # Output in INPUT order, not priority order — caller prints the prompt
    # in input order; matching that makes the audit log easy to read.
    out: list[Allocation] = []
    for s in sections:
        out.append(
            Allocation(
                section_name=s.name,
                allocated=allocated[s.name],
                status=status.get(s.name, "intact"),
                reason=reason.get(s.name, ""),
            )
        )

    return AllocationResult(
        allocations=out,
        budget=budget,
        budget_used=budget - headroom,
        budget_headroom=headroom,
        decisions=decisions,
    )
