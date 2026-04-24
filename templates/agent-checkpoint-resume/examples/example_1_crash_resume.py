#!/usr/bin/env python3
"""Example 1: clean crash-and-resume.

Mission of 4 steps. Steps 0 and 1 commit. The host is killed mid-step 2
(only step_begin, no step_end). On restart, plan_resume walks the
checkpoint, sees the unmatched begin, and returns next_step_index=2 so
the runner re-executes from step 2 without redoing 0/1.
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

# Simulate the deterministic planner: input to step N is (prompt, accumulated outputs[:N]).
PROMPT = {"mission": "build-summary-report", "model": "m-1"}
STEP_OUTPUTS = ["scout-result", "scout-summary", "draft-report", "final-report"]


def step_input(idx: int) -> dict:
    return {"prompt": PROMPT, "prior": STEP_OUTPUTS[:idx]}


# --- run 1: commit steps 0, 1; crash mid-step 2 ---
for idx in (0, 1):
    sid = f"s{idx}"
    ih = canonical_hash(step_input(idx))
    append_begin(log, step_id=sid, step_index=idx,
                 input_hash=ih, tools_planned=["tool_a"], ts=1700000000 + idx * 10)
    oh = canonical_hash({"out": STEP_OUTPUTS[idx]})
    append_end(log, step_id=sid, step_index=idx,
               output_hash=oh, tools_called=["tool_a"],
               exit_state="continue", ts=1700000005 + idx * 10)

# Crash: only the begin for step 2 is written.
append_begin(log, step_id="s2", step_index=2,
             input_hash=canonical_hash(step_input(2)),
             tools_planned=["tool_b"], ts=1700000020)
print("--- crash ---")
print(open(log).read())

# --- restart: planner recomputes expected hashes for the same plan ---
expected = {i: canonical_hash(step_input(i)) for i in range(4)}
records = load_checkpoint(log)
plan = plan_resume(records, expected)
print("resume plan:")
print(json.dumps(plan.to_dict(), indent=2, sort_keys=True))
