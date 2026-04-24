#!/usr/bin/env python3
"""
dedup-replay.py — simulate a tool-host's dedup-table behaviour.

Stdlib only. Reads a `scenario.json` (see examples/) and prints the
sequence of requests, host responses, and dedup-table state.

Scenario schema:
{
  "scope": {"tenant": "...", "session": "..."},
  "requests": [
    {
      "envelope_request": { ... },         # full request envelope
      "side_effect_succeeds": true,        # would the side effect work?
      "transport_succeeds": true,          # does the response arrive?
      "now_ms": 1745557180000              # simulated wall clock
    }, ...
  ]
}

For each request, the simulator:
  1. Derives the key (using bin/derive-key.py rules).
  2. Looks it up in the in-memory dedup table.
  3. Returns the appropriate response envelope.
  4. Updates the table on `executed_now`.

The output is deterministic given the scenario, which is the whole
point: every example in this template can be re-run to verify the
claimed outcome.
"""

from __future__ import annotations
import argparse
import json
import os
import sys

# Reuse the real key-derivation logic.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from importlib import util as _il_util
_spec = _il_util.spec_from_file_location(
    "_dk", os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "derive-key.py"))
_dk = _il_util.module_from_spec(_spec)
_spec.loader.exec_module(_dk)  # type: ignore


def simulate(scenario):
    scope = scenario["scope"]
    table = {}  # idempotency_key -> row
    transcript = []

    for step_i, step in enumerate(scenario["requests"], 1):
        req = step["envelope_request"]
        env = req["envelope"]
        now = step["now_ms"]

        # Derive (or trust the request's stated key — must match).
        derived = _dk.derive_key(req, scope)
        if env["idempotency_key"] != derived:
            transcript.append({
                "step": step_i,
                "outcome": "ASSERTION_FAILED",
                "detail": f"stated key {env['idempotency_key']!r} "
                          f"!= derived {derived!r}",
            })
            continue
        key = derived

        # Identity-fields canonical for collision detection.
        identity = _dk._pick(req["arguments"],
                             _dk.IDENTITY_FIELDS[req["tool_name"]])
        identity_canon = json.dumps(identity, sort_keys=True,
                                    separators=(",", ":"))

        # max_attempts ceiling.
        if env["attempt_number"] > env["max_attempts"]:
            transcript.append({
                "step": step_i,
                "outcome": "rejected_max_attempts",
                "key": key,
                "attempt": env["attempt_number"],
            })
            continue

        # deadline check.
        if now > env["deadline"]:
            transcript.append({
                "step": step_i,
                "outcome": "expired",
                "key": key,
                "now_ms": now,
                "deadline_ms": env["deadline"],
            })
            continue

        # Lookup.
        row = table.get(key)
        if row is not None:
            if row["identity_fields_canonical"] != identity_canon:
                transcript.append({
                    "step": step_i,
                    "outcome": "rejected_key_collision",
                    "key": key,
                    "stored_identity": row["identity_fields_canonical"],
                    "incoming_identity": identity_canon,
                })
                continue
            transcript.append({
                "step": step_i,
                "outcome": "replayed_from_cache",
                "key": key,
                "original_attempt_number": row["attempt_number"],
                "executed_at": row["executed_at"],
                "result": row["result_json"],
            })
            continue

        # Miss — try to execute.
        if not step.get("side_effect_succeeds", True):
            transcript.append({
                "step": step_i,
                "outcome": "side_effect_failed",
                "key": key,
                "note": "host did not write to dedup table",
            })
            continue

        # Side effect succeeds. We always write the row BEFORE
        # attempting transport, so a transport failure still leaves
        # the dedup row intact for the retry to replay.
        result = step.get("simulated_result", {"ok": True, "step": step_i})
        table[key] = {
            "tool_name": req["tool_name"],
            "identity_fields_canonical": identity_canon,
            "result_json": result,
            "executed_at": now,
            "attempt_number": env["attempt_number"],
            "expires_at": now + 24 * 3600 * 1000,
        }

        if not step.get("transport_succeeds", True):
            transcript.append({
                "step": step_i,
                "outcome": "executed_now_BUT_TRANSPORT_DROPPED",
                "key": key,
                "executed_at": now,
                "note": "row written; agent will not see result; "
                        "expect a retry to replay_from_cache",
            })
            continue

        transcript.append({
            "step": step_i,
            "outcome": "executed_now",
            "key": key,
            "executed_at": now,
            "attempt_number": env["attempt_number"],
            "result": result,
        })

    return {"transcript": transcript,
            "final_table_size": len(table),
            "final_keys": sorted(table.keys())}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("scenario", help="scenario.json")
    args = p.parse_args()
    with open(args.scenario) as f:
        scenario = json.load(f)
    out = simulate(scenario)
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
