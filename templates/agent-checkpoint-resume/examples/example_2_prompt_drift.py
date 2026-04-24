#!/usr/bin/env python3
"""Example 2: prompt drift invalidates a committed checkpoint.

Run 1 commits steps 0 and 1 cleanly, then exits. Between runs, the
operator edits the system prompt — so when run 2's planner recomputes
input_hash for step 1, it no longer matches what was committed. The
engine returns state="invalidated" pointing at s1, refusing to silently
fast-forward past stale work.
"""

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from checkpoint import (  # noqa: E402
    append_begin, append_end, canonical_hash, load_checkpoint, plan_resume,
)

tmpdir = tempfile.mkdtemp(prefix="ckpt-")
log = os.path.join(tmpdir, "mission.jsonl")

PROMPT_V1 = {"mission": "build-summary-report", "model": "m-1", "system": "v1"}
STEP_OUTPUTS = ["scout-result", "scout-summary", "draft-report", "final-report"]


def step_input(prompt: dict, idx: int) -> dict:
    return {"prompt": prompt, "prior": STEP_OUTPUTS[:idx]}


# --- run 1: commit steps 0 and 1 cleanly ---
for idx in (0, 1):
    sid = f"s{idx}"
    ih = canonical_hash(step_input(PROMPT_V1, idx))
    append_begin(log, step_id=sid, step_index=idx,
                 input_hash=ih, tools_planned=["tool_a"], ts=1700000000 + idx * 10)
    oh = canonical_hash({"out": STEP_OUTPUTS[idx]})
    append_end(log, step_id=sid, step_index=idx,
               output_hash=oh, tools_called=["tool_a"],
               exit_state="continue", ts=1700000005 + idx * 10)

print("--- run 1 committed checkpoint (2 steps clean) ---")
print(open(log).read())

# --- between-runs prompt edit ---
PROMPT_V2 = {**PROMPT_V1, "system": "v2-tightened"}

# --- run 2: planner recomputes hashes against the new prompt ---
expected = {i: canonical_hash(step_input(PROMPT_V2, i)) for i in range(4)}
records = load_checkpoint(log)
plan = plan_resume(records, expected)
print("resume plan after prompt edit:")
print(json.dumps(plan.to_dict(), indent=2, sort_keys=True))
print()
print("operator action: review s1, then either (a) truncate the log to "
      "before s1 and rerun, (b) keep PROMPT_V1 for this mission, or "
      "(c) acknowledge with a force-accept flag in the host.")
