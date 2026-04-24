# Decision-log emitter prompt

Use to produce one decision-log line per agent step in the canonical
shape defined by `SPEC.md`. The prompt is meant for an agent that
already knows the inputs (mission_id, step_index, prompt_hash,
model, tools_called, exit_state) and just needs to assemble them
into the correct JSON shape.

In a normal pipeline the host code emits this directly without
involving the model. This prompt exists for cases where the agent
itself is asked to produce its own decision record (self-reporting
agents, reflective traces).

## System

```
You are emitting one record of an append-only decision log. Output
STRICT JSON with EXACTLY these eight required keys, in any key
order:

  ts            (string, ISO-8601 UTC, e.g. "2026-04-24T17:00:00Z")
  mission_id    (string)
  step_id       (string)
  step_index    (integer >= 0)
  prompt_hash   (string matching ^sha256:[0-9a-f]{64}$)
  model         (string)
  tools_called  (array of objects, each {name: str, ok: bool, duration_ms: int >= 0})
  exit_state    (one of: "continue", "done", "handoff", "giveup", "error")

You MAY include any of these optional keys: exit_reason (string),
tokens_in (int), tokens_out (int), parent_step_id (string),
notes (string). Do not invent other keys.

Do NOT include any text outside the JSON object. Do NOT wrap in a
code fence. Output exactly one line.
```

## User template

```
Inputs:
{inputs_json}
```

`inputs_json` is a JSON object with the eight required values plus
any optional ones the host wants to include.

## Caller contract

- Caller validates the line through `bin/decision_log_validate.py`
  before appending to the log file.
- On validation failure, the caller logs the offending output to a
  side-channel quarantine file and emits a synthetic record with
  `exit_state="error"` and `notes="self-report failed validation"`.
- The agent never emits more than one line per step.
