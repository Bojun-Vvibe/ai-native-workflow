#!/usr/bin/env python3
"""Partial-failure aggregator for fan-out tool calls.

Given N independent tool-call results, each with status `ok|error|timeout|skipped`,
produce a single structured verdict for the orchestrator:

    {
      "verdict": "all_ok" | "partial_ok" | "all_failed" | "quorum_ok" | "quorum_failed",
      "ok_count": int,
      "fail_count": int,
      "skipped_count": int,
      "total": int,
      "policy": {...echo of input...},
      "by_id": {id: {"status": ..., "error_class": ...}},
      "first_failure": {"id": ..., "status": ..., "error_class": ...} | null,
      "advice": "proceed" | "proceed_degraded" | "retry_failed_only" | "abort"
    }

Pure function. Stdlib only. Deterministic ordering.

Why a dedicated aggregator: when an agent fans out K tool calls (parallel reads,
multi-region writes, multi-source RAG fetches) it must make ONE downstream
decision. Ad-hoc `all(ok)` collapses partial-success information; raising on
first failure throws away the K-1 successful results. This template gives a
named verdict + actionable advice so the orchestrator's branching is uniform
across missions.

CLI:
    aggregate.py policy.json results.json   # exits 0 (proceed*), 1 (retry), 2 (abort)
"""
from __future__ import annotations

import json
import sys
from typing import Any

OK_STATES = {"ok"}
FAIL_STATES = {"error", "timeout"}
SKIP_STATES = {"skipped"}
ALL_STATES = OK_STATES | FAIL_STATES | SKIP_STATES


def aggregate(policy: dict, results: list[dict]) -> dict:
    """Pure aggregation. `policy` keys:

        mode: "all" | "quorum"            (required)
        quorum: int                       (required if mode=="quorum")
        skipped_counts_as: "ok"|"fail"|"ignore"  (default "ignore")
    """
    mode = policy.get("mode")
    if mode not in ("all", "quorum"):
        raise ValueError(f"policy.mode must be 'all' or 'quorum', got {mode!r}")
    if mode == "quorum":
        q = policy.get("quorum")
        if not isinstance(q, int) or q < 1:
            raise ValueError("policy.quorum must be a positive int when mode=='quorum'")
    skip_rule = policy.get("skipped_counts_as", "ignore")
    if skip_rule not in ("ok", "fail", "ignore"):
        raise ValueError("policy.skipped_counts_as must be ok|fail|ignore")

    by_id: dict[str, dict] = {}
    seen_ids: list[str] = []
    ok = fail = skipped = 0
    first_failure = None

    for r in results:
        rid = r.get("id")
        if not isinstance(rid, str) or not rid:
            raise ValueError("each result must have a non-empty string 'id'")
        if rid in by_id:
            raise ValueError(f"duplicate result id: {rid!r}")
        status = r.get("status")
        if status not in ALL_STATES:
            raise ValueError(f"result {rid!r} has invalid status {status!r}")
        entry = {"status": status, "error_class": r.get("error_class")}
        by_id[rid] = entry
        seen_ids.append(rid)

        effective = status
        if status in SKIP_STATES:
            if skip_rule == "ok":
                effective = "ok"
            elif skip_rule == "fail":
                effective = "error"
            # else: ignore => stays "skipped"

        if effective in OK_STATES:
            ok += 1
        elif effective in FAIL_STATES:
            fail += 1
            if first_failure is None:
                first_failure = {"id": rid, "status": status,
                                 "error_class": r.get("error_class")}
        else:
            skipped += 1

    total = len(results)

    if mode == "all":
        if total == 0:
            verdict = "all_failed"
        elif fail == 0 and ok == total:
            verdict = "all_ok"
        elif ok == 0:
            verdict = "all_failed"
        else:
            verdict = "partial_ok"
    else:  # quorum
        q = policy["quorum"]
        if ok >= q:
            verdict = "quorum_ok"
        else:
            verdict = "quorum_failed"

    if verdict == "all_ok":
        advice = "proceed"
    elif verdict == "quorum_ok":
        advice = "proceed_degraded" if fail > 0 else "proceed"
    elif verdict == "partial_ok":
        advice = "retry_failed_only"
    else:  # all_failed | quorum_failed
        advice = "abort"

    return {
        "verdict": verdict,
        "ok_count": ok,
        "fail_count": fail,
        "skipped_count": skipped,
        "total": total,
        "policy": policy,
        "by_id": {rid: by_id[rid] for rid in seen_ids},
        "first_failure": first_failure,
        "advice": advice,
    }


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(f"usage: {argv[0]} <policy.json> <results.json>", file=sys.stderr)
        return 2
    with open(argv[1]) as f:
        policy = json.load(f)
    with open(argv[2]) as f:
        results = json.load(f)
    out = aggregate(policy, results)
    print(json.dumps(out, indent=2, sort_keys=False))
    if out["advice"] in ("proceed", "proceed_degraded"):
        return 0
    if out["advice"] == "retry_failed_only":
        return 1
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
