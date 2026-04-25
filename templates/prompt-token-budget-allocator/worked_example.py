"""Worked example: prompt-token-budget-allocator.

Three scenarios:

  1. Comfortable budget — every section gets its ideal allocation.
  2. Tight budget — low-priority docs get truncated, examples dropped.
  3. Pathological budget — a priority-0 floor cannot fit, raises BudgetTooSmall.

Run with:

    python3 templates/prompt-token-budget-allocator/worked_example.py
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from allocator import (  # noqa: E402
    BudgetTooSmall,
    Section,
    allocate,
)


def _show(label: str, sections: list[Section], budget: int) -> None:
    print("=" * 72)
    print(label)
    print(f"budget = {budget}")
    print("-" * 72)
    print("sections:")
    for s in sections:
        print(
            f"  {s.name:<20} priority={s.priority}  "
            f"min={s.min_tokens:<5} ideal={s.ideal_tokens:<5} "
            f"current={s.current_tokens}"
        )
    print("-" * 72)
    res = allocate(sections, budget)
    print(f"budget_used     : {res.budget_used}")
    print(f"budget_headroom : {res.budget_headroom}")
    print("allocations     :")
    for a in res.allocations:
        tag = a.status.upper()
        line = f"  {a.section_name:<20} {tag:<10} allocated={a.allocated}"
        if a.reason:
            line += f"   ({a.reason})"
        print(line)
    print("decisions       :")
    for d in res.decisions:
        print(f"  - {d}")
    print()
    return res


def scenario_1_comfortable() -> None:
    sections = [
        Section("system", priority=0, min_tokens=120, ideal_tokens=120, current_tokens=120),
        Section("instructions", priority=1, min_tokens=200, ideal_tokens=400, current_tokens=400),
        Section("recent_chat", priority=2, min_tokens=200, ideal_tokens=600, current_tokens=600),
        Section("retrieved_docs", priority=3, min_tokens=300, ideal_tokens=1200, current_tokens=1200),
        Section("few_shot_examples", priority=4, min_tokens=400, ideal_tokens=800, current_tokens=800),
    ]
    res = _show("scenario 1: comfortable budget (4000 tokens)", sections, budget=4000)
    # Every section intact, headroom remaining.
    for a in res.allocations:
        assert a.status == "intact", a
    assert res.budget_headroom == 4000 - (120 + 400 + 600 + 1200 + 800)


def scenario_2_tight() -> None:
    sections = [
        Section("system", priority=0, min_tokens=120, ideal_tokens=120, current_tokens=120),
        Section("instructions", priority=1, min_tokens=200, ideal_tokens=400, current_tokens=400),
        Section("recent_chat", priority=2, min_tokens=200, ideal_tokens=600, current_tokens=600),
        Section("retrieved_docs", priority=3, min_tokens=300, ideal_tokens=1200, current_tokens=1200),
        Section("few_shot_examples", priority=4, min_tokens=400, ideal_tokens=800, current_tokens=800),
        # Empty optional section to prove skipped_empty path.
        Section("scratchpad", priority=5, min_tokens=0, ideal_tokens=200, current_tokens=0),
    ]
    # Budget is tight: floors sum to 120+200+200+300+400 = 1220.
    # Pick 1500 so floors fit, top-up has 280 headroom — won't satisfy
    # everyone's ideal; lower-priority sections will be truncated/dropped.
    res = _show("scenario 2: tight budget (1500 tokens)", sections, budget=1500)
    assert res.by_name("system").status == "intact"
    assert res.by_name("instructions").status in ("intact", "truncated")
    # Recent_chat at p=2 should win at least its floor in top-up over examples at p=4.
    assert res.by_name("recent_chat").allocated >= 200
    # Examples at p=4 should be at or near floor (400) — strictly truncated.
    assert res.by_name("few_shot_examples").status == "truncated"
    assert res.by_name("scratchpad").status == "skipped_empty"
    # Total used must exactly equal budget - headroom.
    total = sum(a.allocated for a in res.allocations)
    assert total == res.budget_used
    assert res.budget_headroom >= 0


def scenario_3_pathological() -> None:
    sections = [
        Section("system", priority=0, min_tokens=2000, ideal_tokens=2000, current_tokens=2000),
        Section("user_query", priority=0, min_tokens=300, ideal_tokens=300, current_tokens=300),
    ]
    print("=" * 72)
    print("scenario 3: pathological — priority=0 floor doesn't fit, raises")
    print(f"budget = 1000   (system floor alone is 2000)")
    print("-" * 72)
    try:
        allocate(sections, budget=1000)
    except BudgetTooSmall as e:
        print(f"BudgetTooSmall raised as expected: {e}")
    else:
        raise AssertionError("expected BudgetTooSmall")
    print()


def scenario_4_drop_optional() -> None:
    # An explicit "should drop the optional section" case for clarity.
    sections = [
        Section("system", priority=0, min_tokens=100, ideal_tokens=100, current_tokens=100),
        Section("user_query", priority=0, min_tokens=200, ideal_tokens=200, current_tokens=200),
        # A bulky optional section that should be dropped because its floor
        # cannot fit in the residual headroom.
        Section("rag_docs", priority=3, min_tokens=500, ideal_tokens=900, current_tokens=900),
        # A small low-priority section whose floor *does* fit and should be
        # included.
        Section("style_hint", priority=4, min_tokens=40, ideal_tokens=40, current_tokens=40),
    ]
    res = _show("scenario 4: drop the bulky optional, keep the small one",
                sections, budget=400)
    assert res.by_name("rag_docs").status == "dropped"
    assert "floor_did_not_fit" in res.by_name("rag_docs").reason
    assert res.by_name("style_hint").status == "intact"
    assert res.by_name("system").status == "intact"
    assert res.by_name("user_query").status == "intact"


def main() -> int:
    scenario_1_comfortable()
    scenario_2_tight()
    scenario_3_pathological()
    scenario_4_drop_optional()
    print("all invariants OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
