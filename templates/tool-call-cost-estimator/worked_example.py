"""Worked example: pre-flight cost estimate + gate + model picker.

Run: python3 worked_example.py
"""
from __future__ import annotations

import json

from estimator import (
    CallPlan,
    cheapest_model_that_fits,
    estimate,
    gate,
)


def section(title: str) -> None:
    print()
    print("=" * 64)
    print(title)
    print("=" * 64)


def main() -> None:
    # A representative agent prompt: short system, real user task,
    # two retrieved doc snippets, planned 600-token answer.
    system_prompt = (
        "You are a precise code-review assistant. Always cite filenames "
        "and line numbers. If you are unsure, say so."
    )
    user_prompt = (
        "Review the following diff for the auth-token refresh logic. "
        "Flag any path where a stale token can be returned to a caller "
        "after a refresh failure. Suggest a minimal fix."
    )
    extras = [
        # retrieved doc 1: the file under review (truncated for the example)
        "def refresh_token(session):\n"
        "    try:\n"
        "        new = session.post('/refresh').json()['token']\n"
        "        session.token = new\n"
        "    except Exception:\n"
        "        pass\n"
        "    return session.token\n",
        # retrieved doc 2: a related contract spec
        "Contract: refresh_token MUST raise on failure; callers MUST "
        "treat a returned value as a known-good fresh token.",
    ]

    plan = CallPlan(
        model="mid-balanced",
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        extras=extras,
        max_completion_tokens=600,
    )

    section("1. Bare estimate against the planned model")
    est = estimate(plan)
    print(json.dumps(est.to_dict(), indent=2))

    section("2. Per-call cost gate (ceiling = $0.005)")
    d = gate(plan, max_cost_usd=0.005)
    print(f"allow={d.allow}  reason={d.reason!r}")
    print(f"estimated max cost: ${d.estimate.total_cost_usd_max:.5f}")

    section("3. Same plan, but on the expensive model")
    plan_big = CallPlan(
        model="big-smart",
        system_prompt=plan.system_prompt,
        user_prompt=plan.user_prompt,
        extras=plan.extras,
        max_completion_tokens=plan.max_completion_tokens,
    )
    d_big = gate(plan_big, max_cost_usd=0.005)
    print(f"allow={d_big.allow}  reason={d_big.reason!r}")
    print(f"estimated max cost: ${d_big.estimate.total_cost_usd_max:.5f}")

    section("4. Cheapest model that satisfies a $0.01 ceiling")
    pick = cheapest_model_that_fits(
        plan,
        candidates=["small-fast", "mid-balanced", "big-smart"],
        max_cost_usd=0.01,
    )
    if pick is None:
        print("no candidate fits the budget")
    else:
        model, picked_est = pick
        print(f"picked: {model}")
        print(f"max cost: ${picked_est.total_cost_usd_max:.5f}")
        print(f"prompt tokens: {picked_est.prompt_tokens}  "
              f"context fill: {picked_est.context_fill_ratio:.2%}")

    section("5. Context-fill gate (huge prompt, small model)")
    huge_plan = CallPlan(
        model="small-fast",
        system_prompt=plan.system_prompt,
        # simulate a large retrieved-context blob: ~4000 words of filler
        user_prompt=plan.user_prompt + ("\n\n" + ("alpha bravo charlie delta " * 1000)),
        extras=plan.extras,
        max_completion_tokens=200,
    )
    d_huge = gate(huge_plan, max_cost_usd=10.0, max_context_fill=0.50)
    print(f"allow={d_huge.allow}  reason={d_huge.reason!r}")
    print(f"prompt tokens: {d_huge.estimate.prompt_tokens}  "
          f"fill: {d_huge.estimate.context_fill_ratio:.2%}")


if __name__ == "__main__":
    main()
