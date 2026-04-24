#!/usr/bin/env python3
"""llm-output-trust-tiers — pure tier router for LLM outputs.

Given a structured *evidence record* about an LLM output, decide which
trust tier it belongs to and what the orchestrator should do with it.

Tiers (ordered, most to least trusted):
    auto_apply     — apply without human review
    shadow_apply   — apply but mark for sampling / async review
    human_review   — block until a human signs off
    quarantine     — never apply; store for forensics

Routing is a *pure function* of:
  - validator outcomes (`schema_ok`, `repair_count`)
  - source class (`source_class`: `pinned_eval` / `cached_known` / `fresh`)
  - blast radius (`blast_radius`: `read_only` / `reversible` / `irreversible`)
  - canary status (`canary_passed`: bool | null)
  - explicit caller override (`override_tier`, optional)

Decision rules are layered so that ANY single hard fail forces
quarantine; demotions stack (you can be demoted from `auto_apply` all
the way to `human_review` by independent hits).

Usage:

    classify_trust_tier.py < evidence.jsonl

Each input line is a JSON object describing one output. Each output
line is `{ "id": ..., "tier": ..., "reasons": [...] }`.

Exit codes:
    0 — all outputs landed in {auto_apply, shadow_apply}
    1 — at least one output requires human_review
    2 — at least one output is quarantined (or input malformed)

Composes with:
    agent-output-validation        provides schema_ok / repair_count
    structured-output-repair-loop  same; defines `repair_count`
    agent-trace-redaction-rules    quarantined outputs are still safe
                                    to export as redacted forensic data
    structured-error-taxonomy      a `tool_bad_input` error class on the
                                    upstream call should set source_class
                                    to `fresh` even if cache says hit
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

TIERS = ("auto_apply", "shadow_apply", "human_review", "quarantine")
SOURCE_CLASSES = ("pinned_eval", "cached_known", "fresh")
BLAST = ("read_only", "reversible", "irreversible")

# Tier rank: lower number = more trusted
RANK = {t: i for i, t in enumerate(TIERS)}


def _demote(current: str, target: str) -> str:
    """Return whichever tier is *less* trusted (higher rank)."""
    return target if RANK[target] > RANK[current] else current


def classify(rec: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(rec, dict):
        raise ValueError("record must be an object")
    if "id" not in rec or not isinstance(rec["id"], str):
        raise ValueError("missing or non-string 'id'")

    schema_ok = bool(rec.get("schema_ok", False))
    repair_count = int(rec.get("repair_count", 0))
    source_class = rec.get("source_class", "fresh")
    blast = rec.get("blast_radius", "irreversible")
    canary = rec.get("canary_passed", None)
    override = rec.get("override_tier", None)

    if source_class not in SOURCE_CLASSES:
        raise ValueError(f"bad source_class: {source_class!r}")
    if blast not in BLAST:
        raise ValueError(f"bad blast_radius: {blast!r}")
    if override is not None and override not in TIERS:
        raise ValueError(f"bad override_tier: {override!r}")

    reasons: list[str] = []

    # Hard fails — straight to quarantine, regardless of anything else.
    # An override CANNOT promote a quarantined output (only demote).
    if not schema_ok:
        return {
            "id": rec["id"],
            "tier": "quarantine",
            "reasons": ["schema_invalid"],
        }
    if repair_count < 0:
        raise ValueError("repair_count must be >= 0")
    if repair_count > 3:
        return {
            "id": rec["id"],
            "tier": "quarantine",
            "reasons": [f"repair_count_over_threshold:{repair_count}"],
        }

    # Start optimistic, then demote.
    tier = "auto_apply"

    if repair_count >= 1:
        tier = _demote(tier, "shadow_apply")
        reasons.append(f"repair_count:{repair_count}")
    if repair_count >= 2:
        tier = _demote(tier, "human_review")
        # reason already added above, just mark severity
        reasons.append("repair_count_high")

    if source_class == "fresh":
        tier = _demote(tier, "shadow_apply")
        reasons.append("source_fresh")
    elif source_class == "cached_known":
        # no demotion; cached_known is the "default trust" rung
        pass
    else:  # pinned_eval — no demotion; this is the most trusted source
        pass

    if blast == "irreversible":
        tier = _demote(tier, "human_review")
        reasons.append("blast_irreversible")
    elif blast == "reversible":
        # only demote past auto_apply if combined with another flag
        if tier == "auto_apply" and (source_class == "fresh" or repair_count >= 1):
            tier = _demote(tier, "shadow_apply")
            reasons.append("blast_reversible_with_risk")

    if canary is False:
        tier = _demote(tier, "human_review")
        reasons.append("canary_failed")
    # canary True or None does not affect tier

    # Override can only DEMOTE (never promote past quarantine, never up-rank).
    if override is not None:
        if RANK[override] > RANK[tier]:
            reasons.append(f"override_demoted_to:{override}")
            tier = override
        else:
            reasons.append(f"override_ignored_would_promote:{override}")

    if not reasons:
        reasons.append("clean")

    return {"id": rec["id"], "tier": tier, "reasons": reasons}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--in", dest="infile", default="-",
                   help="input JSONL path (default: stdin)")
    args = p.parse_args(argv)

    src = sys.stdin if args.infile == "-" else open(args.infile, "r", encoding="utf-8")
    saw_quarantine = False
    saw_human = False
    line_no = 0
    try:
        for raw in src:
            line_no += 1
            raw = raw.strip()
            if not raw:
                continue
            try:
                rec = json.loads(raw)
            except json.JSONDecodeError as e:
                sys.stderr.write(f"line {line_no}: bad JSON: {e}\n")
                return 2
            try:
                out = classify(rec)
            except ValueError as e:
                sys.stderr.write(f"line {line_no}: {e}\n")
                return 2
            print(json.dumps(out, sort_keys=True))
            if out["tier"] == "quarantine":
                saw_quarantine = True
            elif out["tier"] == "human_review":
                saw_human = True
    finally:
        if src is not sys.stdin:
            src.close()
    if saw_quarantine:
        return 2
    if saw_human:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
