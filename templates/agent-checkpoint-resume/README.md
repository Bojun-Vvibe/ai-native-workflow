# agent-checkpoint-resume

Append-only JSONL checkpoint format + deterministic resume engine for
long-running agent missions. Survives crash, kill-9, OOM, host
preemption, and unattended overnight runs without re-doing committed
work — and refuses to silently fast-forward when prompt drift means
the committed work would no longer match what the planner is now
producing.

## Problem

Long agent missions (multi-hour sweeps, overnight digests, batch
review jobs) hit one of three bad outcomes when the host dies mid-run:

1. **No checkpoint at all.** The mission restarts from step 0,
   re-spending tokens and re-doing tool calls (expensive at best,
   unsafe at worst — a non-idempotent tool re-run is data corruption,
   see `tool-call-retry-envelope`).
2. **Process-memory-only checkpoint.** The runner has a `current_step`
   counter in RAM. SIGKILL takes it with the process; restart starts
   over.
3. **Naive checkpoint that doesn't notice drift.** The runner persists
   `last_completed_step=5` to disk, restarts at step 6, and happily
   continues — even though the operator edited the system prompt
   between runs and step 5's output is now incompatible with the new
   plan. The mission silently produces a Frankenstein result.

A real checkpoint must answer two distinct questions on resume:

- **Where did we crash?** (find the boundary)
- **Is what's already on disk still trustworthy?** (validate it)

## Design

### Two-record-per-step format

Every step writes two JSONL records, fsynced on append:

```json
{"kind":"step_begin","step_id":"s2","step_index":2,"input_hash":"...","tools_planned":["fs.write"],"ts":1700000020}
{"kind":"step_end","step_id":"s2","step_index":2,"output_hash":"...","tools_called":["fs.write"],"exit_state":"continue","ts":1700000025}
```

A step is **committed** iff both records exist *and* they pair on
`step_id`. A `step_begin` without a matching `step_end` means the host
died mid-step; that step must be redone.

`exit_state` uses the same enum as
[`agent-decision-log-format`](../agent-decision-log-format/) so the
two logs compose without translation.

### Hash-based drift detection

`input_hash` is the canonical-JSON SHA-256 of `{prompt, prior_outputs}`
— everything the planner consumed to produce step `N`. On resume the
planner recomputes the expected `input_hash` for each step starting
from index 0, given its **current** prompt + model + earlier-output
state.

`plan_resume(records, expected_hashes)` walks committed records in
order. The first `input_hash` mismatch returns `state="invalidated"`
with the offending `step_id` — never silently past-it. The operator
chooses: truncate the log, pin the old prompt, or force-accept.

### Four resume states

| state | meaning | next action |
|---|---|---|
| `fresh` | no checkpoint exists | start at step 0 |
| `resume` | clean checkpoint, possibly with one mid-step crash | start at `next_step_index` |
| `invalidated` | committed step's `input_hash` no longer matches planner | stop; surface `invalidated_step_id` for human review |
| `complete` | last committed step has `exit_state="done"` | nothing to do |

### Why `output_hash` is recorded but not validated on resume

`output_hash` exists so a *separate* auditor can later verify "the
output we re-used as `prior` for step N+1 is exactly the bytes step N
wrote". The resume engine itself doesn't validate it — that would
require re-executing step N to re-derive the bytes, defeating the
point of resumption. The hash makes after-the-fact tamper detection
cheap.

## Files

- [`checkpoint.py`](checkpoint.py) — stdlib-only engine + CLI; pure
  `plan_resume()` function; `append_begin` / `append_end` helpers
  with `os.fsync` on every write.
- [`examples/example_1_crash_resume.py`](examples/example_1_crash_resume.py)
  — clean crash mid-step 2, resume picks up at step 2.
- [`examples/example_2_prompt_drift.py`](examples/example_2_prompt_drift.py)
  — committed checkpoint, system-prompt edit between runs, engine
  refuses to fast-forward.

## CLI usage

```sh
python3 checkpoint.py mission.jsonl expected_hashes.json
```

Where `expected_hashes.json` is `{"0": "<sha256>", "1": "<sha256>", ...}`
recomputed by the planner. Exits `0` on `fresh`/`resume`/`complete`,
`1` on `invalidated` (so CI / supervisors can wedge until a human
looks).

## Worked examples

### Example 1 — crash mid-step, clean resume

Steps 0 and 1 commit. The host dies after writing step 2's `step_begin`
but before its `step_end`. Restart finds the unmatched begin and
returns `state="resume", next_step_index=2`.

```
$ python3 examples/example_1_crash_resume.py
--- crash ---
{"input_hash":"3d8cb1f64ebbcf31ed030caaa38c545688d19899ab7ffd88d733cf8f95cb15a8","kind":"step_begin","step_id":"s0","step_index":0,"tools_planned":["tool_a"],"ts":1700000000}
{"exit_state":"continue","kind":"step_end","output_hash":"0f78bcbc8dd9fe911ae4ef1f39e886cebe4f4e814ac506c825dd546054a36465","step_id":"s0","step_index":0,"tools_called":["tool_a"],"ts":1700000005}
{"input_hash":"553b96daa5f9185883d7ed6dc223dc21ef153ec7c728af6e0c03dee3aedb1cd8","kind":"step_begin","step_id":"s1","step_index":1,"tools_planned":["tool_a"],"ts":1700000010}
{"exit_state":"continue","kind":"step_end","output_hash":"85bca5c42738baf2541e555c1219645f250902fbf7d710f03124a58398d596c6","step_id":"s1","step_index":1,"tools_called":["tool_a"],"ts":1700000015}
{"input_hash":"b83d6a2119ebda17337569b46d343b8c7b9f2bd8b151793a25605ebcbbb6a904","kind":"step_begin","step_id":"s2","step_index":2,"tools_planned":["tool_b"],"ts":1700000020}

resume plan:
{
  "committed_count": 2,
  "detail": {
    "reason": "uncommitted_step",
    "step_id": "s2"
  },
  "next_step_index": 2,
  "state": "resume"
}
```

What this shows:

- `committed_count: 2` — steps 0 and 1 are intact and re-usable as
  context.
- `next_step_index: 2` — the runner re-executes from step 2, NOT step
  0. The runner must treat step 2 as fresh; if step 2's first attempt
  did any side-effecting tool calls, those tools must be idempotent
  (compose with `tool-call-retry-envelope`'s envelope).
- `detail.reason: "uncommitted_step"` distinguishes "we crashed inside
  this step" from "everything was clean, just resume at the tail".

### Example 2 — prompt drift between runs, engine refuses to fast-forward

Run 1 commits steps 0 and 1 against `system: "v1"`. Between runs the
operator edits the prompt to `system: "v2-tightened"`. On run 2 the
planner recomputes `input_hash` for step 0 using the new prompt and
gets a different hash than what's on disk.

```
$ python3 examples/example_2_prompt_drift.py
--- run 1 committed checkpoint (2 steps clean) ---
{"input_hash":"799529f6e8450fb3623cde87114e5c6bf09c352bcf6b62773cb00605d4b02bb7","kind":"step_begin","step_id":"s0","step_index":0,"tools_planned":["tool_a"],"ts":1700000000}
{"exit_state":"continue","kind":"step_end","output_hash":"0f78bcbc8dd9fe911ae4ef1f39e886cebe4f4e814ac506c825dd546054a36465","step_id":"s0","step_index":0,"tools_called":["tool_a"],"ts":1700000005}
{"input_hash":"b2e73cbd615d2400df06b154789168505491342218c6293b82294e1ca09ae921","kind":"step_begin","step_id":"s1","step_index":1,"tools_planned":["tool_a"],"ts":1700000010}
{"exit_state":"continue","kind":"step_end","output_hash":"85bca5c42738baf2541e555c1219645f250902fbf7d710f03124a58398d596c6","step_id":"s1","step_index":1,"tools_called":["tool_a"],"ts":1700000015}

resume plan after prompt edit:
{
  "committed_count": 0,
  "detail": {
    "expected": "db55536fc1bd8afa130ffe20d6732a91b3a368e14328e6eca72ab695b8508119",
    "found": "799529f6e8450fb3623cde87114e5c6bf09c352bcf6b62773cb00605d4b02bb7",
    "reason": "input_hash_drift"
  },
  "invalidated_step_id": "s0",
  "next_step_index": 0,
  "state": "invalidated"
}
```

What this shows:

- `state: "invalidated"` — the engine refuses to silently fast-forward.
- `invalidated_step_id: "s0"` — drift is caught at the *earliest*
  possible step (s0's `prior` is `[]`, so its `input_hash` depends
  only on the prompt; the prompt change makes s0 immediately
  inconsistent). Catching drift early avoids burning step-1 work on a
  doomed mission.
- `committed_count: 0` — even though run 1 wrote two clean
  step_end records, none survive the drift check. The host MUST NOT
  use the on-disk `prior_outputs` to seed step 1+.
- The `expected` / `found` pair lets a human (or a `pew checkpoint
  diff` tool) compare the two prompt-states quickly.

## Composition

- Pair with [`agent-decision-log-format`](../agent-decision-log-format/)
  by writing the same `step_id` / `step_index` / `exit_state` to both
  logs. The decision log is for observability; the checkpoint log is
  for resumption — same boundaries, different consumers.
- Pair with [`prompt-fingerprinting`](../prompt-fingerprinting/) by
  using the prompt fingerprint as part of the hashed `prompt` blob —
  drift detection becomes free.
- Pair with [`tool-call-retry-envelope`](../tool-call-retry-envelope/)
  for the mid-step crash case: any tool call inside an uncommitted
  step that gets re-executed on resume MUST be retry-safe under the
  envelope's `idempotency_key` rules.
- Pair with [`agent-cost-budget-envelope`](../agent-cost-budget-envelope/)
  to skip ledger entries for steps that the resume plan marks as
  already-committed (don't double-bill resumption).
