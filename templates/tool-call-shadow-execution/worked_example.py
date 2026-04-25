"""Worked example: tool-call-shadow-execution.

Scenario: we are migrating `search_files(query)` from a regex-grep
implementation (production) to a candidate that uses an in-memory index.
We run 6 calls through the harness against the candidate while production
serves the agent. Five buckets are exercised:

  - equal              : both backends return the same hit list
  - value_mismatch     : candidate is missing one path
  - shadow_only_field  : candidate started returning a new `score` field
  - shadow_timeout     : candidate hangs on a pathological query
  - side_effect_violation : a buggy candidate writes to disk despite is_dry_run

After the run we print the report and assert the safe_to_promote() gate.
"""

from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor

from shadow import ShadowRunner, SideEffectGuard


# ---- Production tool: trusted reference ------------------------------------


_FAKE_INDEX = {
    "auth":   ["src/auth.py", "src/sessions.py", "tests/test_auth.py"],
    "render": ["src/render.py", "src/templates.py"],
    "cache":  ["src/cache.py", "src/cache_keys.py"],
    "noop":   [],
    "slow":   ["src/slow.py"],
    "danger": ["src/danger.py"],
}


def prod_search(args: dict) -> dict:
    q = args["query"]
    return {"hits": list(_FAKE_INDEX.get(q, []))}


# ---- Shadow tools (one per scenario) ---------------------------------------


def shadow_equal(args: dict, guard: SideEffectGuard) -> dict:
    assert guard.is_dry_run
    return {"hits": list(_FAKE_INDEX.get(args["query"], []))}


def shadow_missing_one(args: dict, guard: SideEffectGuard) -> dict:
    assert guard.is_dry_run
    hits = list(_FAKE_INDEX.get(args["query"], []))
    if hits:
        hits = hits[:-1]  # drop the last one
    return {"hits": hits}


def shadow_extra_field(args: dict, guard: SideEffectGuard) -> dict:
    assert guard.is_dry_run
    hits = list(_FAKE_INDEX.get(args["query"], []))
    return {"hits": hits, "score": 0.91}  # added a field prod doesn't have


def shadow_hangs(args: dict, guard: SideEffectGuard) -> dict:
    assert guard.is_dry_run
    time.sleep(2.0)  # exceeds shadow_timeout_s=0.2 below
    return {"hits": list(_FAKE_INDEX.get(args["query"], []))}


_VIOLATION_FLAG = {"touched": False}


def shadow_side_effect(args: dict, guard: SideEffectGuard) -> dict:
    """A buggy candidate: ignores is_dry_run and writes."""
    # Pretend to write -- we just flip a flag the harness checks.
    _VIOLATION_FLAG["touched"] = True
    return {"hits": list(_FAKE_INDEX.get(args["query"], []))}


def violation_check() -> bool:
    touched = _VIOLATION_FLAG["touched"]
    _VIOLATION_FLAG["touched"] = False  # reset for next call
    return touched


# ---- Driver ---------------------------------------------------------------


def main() -> None:
    print("=" * 72)
    print("tool-call-shadow-execution :: worked example")
    print("=" * 72)

    with ThreadPoolExecutor(max_workers=2) as ex:
        runner = ShadowRunner(executor=ex, shadow_timeout_s=0.2)

        scenarios = [
            ("c1", "auth",   shadow_equal,        None,            "equal"),
            ("c2", "render", shadow_equal,        None,            "equal"),
            ("c3", "cache",  shadow_missing_one,  None,            "value_mismatch"),
            ("c4", "noop",   shadow_extra_field,  None,            "shadow_only_field"),
            ("c5", "slow",   shadow_hangs,        None,            "shadow_timeout"),
            ("c6", "danger", shadow_side_effect,  violation_check, "side_effect_violation"),
        ]

        for cid, q, sfn, mcheck, expected in scenarios:
            r = runner.execute(
                call_id=cid, tool_name="search_files",
                args={"query": q},
                prod_fn=prod_search,
                shadow_fn=sfn,
                marker_check=mcheck,
            )
            print(f"  [{cid}] q={q!r:9} reason={r.reason:24} status={r.shadow_status:8} detail={r.detail}")
            assert r.reason == expected, (cid, r.reason, expected)

        print()
        print("Report:")
        print(json.dumps(runner.report(), indent=2))

        # safe_to_promote gate
        promote = runner.stats.safe_to_promote(min_samples=6, max_disagreement=0.10)
        print()
        print(f"safe_to_promote(min_samples=6, max_disagreement=0.10): {promote}")
        assert promote is False, "must NOT promote: side_effect_violation present + 4/6 disagreements"

        # Specifically: the side_effect_violation alone must veto promotion
        # even with a generous max_disagreement.
        promote_lenient = runner.stats.safe_to_promote(min_samples=1, max_disagreement=1.0)
        assert promote_lenient is False, "side_effect_violation must veto regardless of thresholds"
        print(f"safe_to_promote(min_samples=1, max_disagreement=1.0)  : {promote_lenient}  (vetoed by unsafe)")

        # Sanity: the bounded sample buffer kept the disagreements (4) and not the equals (2).
        kept = [s.reason for s in runner.stats.samples]
        assert "equal" not in kept
        assert sorted(kept) == ["shadow_only_field", "shadow_timeout", "side_effect_violation", "value_mismatch"]
        print(f"sample buffer kept (no equals): {sorted(kept)}")

    print()
    print("DONE.")


if __name__ == "__main__":
    main()
