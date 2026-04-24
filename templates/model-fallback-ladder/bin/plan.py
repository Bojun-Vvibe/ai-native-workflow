#!/usr/bin/env python3
"""Model fallback ladder.

Given an ordered list of model "rungs" and a per-attempt outcome, climb down
the ladder until a rung succeeds or the ladder is exhausted. Every hop is
recorded with a `reason_class` so the decision log shows *why* each rung was
abandoned.

Pure planner: callers supply a `call_fn(rung, prompt) -> Outcome` so the
ladder logic itself does no I/O and is fully testable with a deterministic
mock.

Outcome shape (returned by caller's `call_fn`):

    {
      "status": "ok" | "error",
      "reason_class": "rate_limited" | "context_overflow" | "5xx"
                    | "timeout" | "content_filter" | "other",   # required iff error
      "tokens_in": int,         # optional, used for skip-rung preflight
      "output": <opaque>        # caller's payload on ok
    }

Ladder rung shape:

    {
      "id": "primary",
      "model": "gpt-vendor-a-large",
      "max_input_tokens": 200000,                 # optional preflight gate
      "skip_on_reason_classes": ["content_filter"]  # optional: classes that
                                                    # also skip THIS rung
                                                    # before trying it
    }

Skip semantics:
- Preflight: if `max_input_tokens` is set on the rung and the prompt's
  `tokens_in` exceeds it, the rung is skipped with reason `preflight_too_long`
  WITHOUT calling `call_fn` (saves the round-trip).
- Reason-class skip: if the previous failed rung's `reason_class` is in this
  rung's `skip_on_reason_classes`, the rung is skipped with reason
  `skip_on_reason_class` (e.g. don't retry a content-filter trip on the same
  vendor's smaller model).

Verdicts:
- `ok` — some rung returned status=ok; `winning_rung_id` set.
- `exhausted` — every rung was tried (or skipped) and none returned ok.

CLI:
    plan.py ladder.json prompt.json mock_outcomes.json
    # exits 0 on ok verdict, 1 on exhausted
"""
from __future__ import annotations

import json
import sys
from typing import Any, Callable

ERROR_CLASSES = {"rate_limited", "context_overflow", "5xx", "timeout",
                 "content_filter", "other"}


def plan(ladder: list[dict], prompt: dict,
         call_fn: Callable[[dict, dict], dict]) -> dict:
    """Pure planner. Walks `ladder` rung-by-rung, calling `call_fn` and
    recording why each rung was abandoned.
    """
    if not isinstance(ladder, list) or not ladder:
        raise ValueError("ladder must be a non-empty list")
    seen_ids = set()
    for r in ladder:
        rid = r.get("id")
        if not isinstance(rid, str) or not rid:
            raise ValueError("each rung must have a non-empty string 'id'")
        if rid in seen_ids:
            raise ValueError(f"duplicate rung id: {rid!r}")
        seen_ids.add(rid)
        if "model" not in r or not isinstance(r["model"], str):
            raise ValueError(f"rung {rid!r} missing 'model'")

    hops: list[dict] = []
    last_failure_class: str | None = None
    winning_rung_id: str | None = None
    winning_output: Any = None
    tokens_in = prompt.get("tokens_in")

    for rung in ladder:
        rid = rung["id"]

        # Reason-class skip (based on PREVIOUS failure)
        skip_classes = rung.get("skip_on_reason_classes") or []
        if last_failure_class is not None and last_failure_class in skip_classes:
            hops.append({
                "rung_id": rid,
                "model": rung["model"],
                "outcome": "skipped",
                "reason_class": "skip_on_reason_class",
                "detail": f"previous_failure={last_failure_class}",
            })
            continue

        # Preflight token-budget skip
        max_in = rung.get("max_input_tokens")
        if isinstance(max_in, int) and isinstance(tokens_in, int) \
                and tokens_in > max_in:
            hops.append({
                "rung_id": rid,
                "model": rung["model"],
                "outcome": "skipped",
                "reason_class": "preflight_too_long",
                "detail": f"tokens_in={tokens_in} max_input_tokens={max_in}",
            })
            # Preflight skip is NOT a model failure; do NOT update
            # last_failure_class, so the next rung's skip rules don't
            # mistake "we never called you" for "you produced a bad class".
            continue

        outcome = call_fn(rung, prompt)
        status = outcome.get("status")
        if status == "ok":
            hops.append({
                "rung_id": rid,
                "model": rung["model"],
                "outcome": "ok",
                "reason_class": None,
                "detail": None,
            })
            winning_rung_id = rid
            winning_output = outcome.get("output")
            return {
                "verdict": "ok",
                "winning_rung_id": winning_rung_id,
                "winning_output": winning_output,
                "hops": hops,
                "rungs_tried": sum(1 for h in hops if h["outcome"] != "skipped"),
                "rungs_skipped": sum(1 for h in hops if h["outcome"] == "skipped"),
            }
        elif status == "error":
            rc = outcome.get("reason_class")
            if rc not in ERROR_CLASSES:
                raise ValueError(
                    f"rung {rid!r} returned error with invalid reason_class={rc!r}")
            hops.append({
                "rung_id": rid,
                "model": rung["model"],
                "outcome": "error",
                "reason_class": rc,
                "detail": outcome.get("detail"),
            })
            last_failure_class = rc
        else:
            raise ValueError(
                f"rung {rid!r} returned invalid status={status!r}")

    return {
        "verdict": "exhausted",
        "winning_rung_id": None,
        "winning_output": None,
        "hops": hops,
        "rungs_tried": sum(1 for h in hops if h["outcome"] != "skipped"),
        "rungs_skipped": sum(1 for h in hops if h["outcome"] == "skipped"),
    }


def _make_mock_call_fn(outcomes_by_rung: dict[str, dict]) -> Callable:
    def call_fn(rung: dict, prompt: dict) -> dict:
        rid = rung["id"]
        if rid not in outcomes_by_rung:
            raise KeyError(f"mock has no outcome for rung_id={rid!r}")
        return outcomes_by_rung[rid]
    return call_fn


def main(argv: list[str]) -> int:
    if len(argv) != 4:
        print(f"usage: {argv[0]} <ladder.json> <prompt.json> "
              f"<mock_outcomes.json>", file=sys.stderr)
        return 2
    with open(argv[1]) as f:
        ladder = json.load(f)
    with open(argv[2]) as f:
        prompt = json.load(f)
    with open(argv[3]) as f:
        outcomes = json.load(f)
    result = plan(ladder, prompt, _make_mock_call_fn(outcomes))
    print(json.dumps(result, indent=2))
    return 0 if result["verdict"] == "ok" else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
