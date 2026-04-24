# Example 02 — broken log surfaces every distinct error code

## What this shows

A six-line input deliberately violates one (or more) of every
distinct rule the validator enforces, so every stable error code in
`SPEC.md` appears at least once in the report:

| Line | Violation(s) | Code(s) |
|---|---|---|
| 2 | `prompt_hash="deadbeef"` (not the sha256 format), `duration_ms=-3` | `bad_hash_format`, `negative_duration` |
| 3 | `ts="not-a-timestamp"`, `exit_state="wishful"`, `step_index` jumps 1 -> 3 | `bad_iso8601`, `bad_enum`, `non_monotonic_step_index` |
| 4 | no `step_index` field; `done` here terminates the mission | `missing_field` |
| 5 | record arrives after the mission's `done`; index jump | `record_after_done`, `non_monotonic_step_index` |
| 6 | not JSON | `parse_error` |

## Run

```bash
python3 ../../bin/decision_log_validate.py decisions.jsonl
```

## Verified output

```json
{
  "errors": [
    {"code": "bad_hash_format", "detail": "prompt_hash does not match sha256:<64hex>", "line": 2, "mission_id": "m_42"},
    {"code": "negative_duration", "detail": "tools_called[0].duration_ms=-3", "line": 2, "mission_id": "m_42"},
    {"code": "bad_enum", "detail": "exit_state 'wishful' not in ['continue', 'done', 'error', 'giveup', 'handoff']", "line": 3, "mission_id": "m_42"},
    {"code": "bad_iso8601", "detail": "ts 'not-a-timestamp' is not ISO-8601 UTC", "line": 3, "mission_id": "m_42"},
    {"code": "non_monotonic_step_index", "detail": "expected step_index=2, got 3", "line": 3, "mission_id": "m_42"},
    {"code": "missing_field", "detail": "missing 'step_index'", "line": 4, "mission_id": "m_42"},
    {"code": "record_after_done", "detail": "mission already terminated by done", "line": 5, "mission_id": "m_42"},
    {"code": "non_monotonic_step_index", "detail": "expected step_index=4, got 5", "line": 5, "mission_id": "m_42"},
    {"code": "parse_error", "detail": "Expecting value: line 1 column 1 (char 0)", "line": 6, "mission_id": "<unknown>"}
  ],
  "input": "decisions.jsonl",
  "invalid_records": 5,
  "missions_completed": 1,
  "missions_seen": 1,
  "total_records": 6,
  "valid_records": 1
}
```

Exit code: `1`.

## What to read from this

- Every error has a `code`, `line`, and `mission_id` so a downstream
  dashboard can group failures by mission and surface the most
  common code over time.
- The validator does not stop at the first error — it keeps walking
  the file so one CI run reports every problem at once.
- `record_after_done` is the rule that catches the most insidious
  bug: an agent loop that "completed" but kept emitting work because
  the orchestrator didn't notice the terminal state.
- `non_monotonic_step_index` self-recovers: after a gap the expected
  counter advances past the offending index, so the validator
  doesn't cascade-flag every later step.
