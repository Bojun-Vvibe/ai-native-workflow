# SPEC: agent-decision-log-format

A canonical, append-only JSONL format for an agent's per-step
decision log. One line per step. Designed for post-hoc audit and
deterministic replay of "what did the agent decide and why?" without
re-running the agent.

## Per-line schema (required fields)

| Field | Type | Meaning |
|---|---|---|
| `ts` | string (ISO-8601 UTC, with `Z`) | Step start timestamp. |
| `mission_id` | string | Stable mission identifier (e.g. ULID). |
| `step_id` | string | Stable per-step identifier; monotonic per mission. |
| `step_index` | integer (>= 0) | Zero-based ordinal of this step within the mission. |
| `prompt_hash` | string (`sha256:` + 64 hex) | Hash of the canonicalised prompt package (system + tools + decoding + convo prefix). |
| `model` | string | Model identifier exactly as sent to the provider. |
| `tools_called` | array of objects | Each object: `{"name": str, "ok": bool, "duration_ms": int >= 0}`. May be empty. |
| `exit_state` | string enum | One of `continue`, `done`, `handoff`, `giveup`, `error`. |

## Optional fields

`exit_reason` (string, free text), `tokens_in` (int), `tokens_out`
(int), `parent_step_id` (string), `notes` (string). Validators MUST
ignore unknown fields (forward compat).

## Hard rules

1. **Append-only.** Once a line is written, it is never edited. Fix
   forward by writing a corrective record with `notes:
   "supersedes step_id=..."`. The validator does not enforce this
   (filesystems can't), but downstream consumers MUST treat a
   rewritten history as corrupt.
2. **No PII in `notes`.** This log is meant to be safe to share for
   audit. Use `agent-trace-redaction-rules` to scrub on export.
3. **`exit_state == "done"` is terminal.** No further records for
   that mission. The validator flags any record with the same
   `mission_id` after a `done`.
4. **`step_index` must be strictly monotonic per mission.** No gaps
   are allowed; the validator flags `step_index` values that don't
   form `0, 1, 2, ...` per mission.
5. **`tools_called[*].duration_ms` must be non-negative.**
6. **`prompt_hash` must match the regex `^sha256:[0-9a-f]{64}$`.**

## Validator exit codes

- `0`: all records valid; no warnings.
- `1`: at least one record failed validation.
- `2`: invalid input (file missing, JSON parse error in arguments).

## Report format

The validator emits a JSON report on stdout:

```json
{
  "input": "decisions.jsonl",
  "total_records": 12,
  "valid_records": 12,
  "invalid_records": 0,
  "missions_seen": 1,
  "missions_completed": 1,
  "errors": []
}
```

Each error has `{line: int, mission_id: str, code: str, detail: str}`.

## Stable error codes

| Code | Meaning |
|---|---|
| `parse_error` | Line is not valid JSON. |
| `missing_field` | A required field is absent. |
| `bad_type` | A field has the wrong JSON type. |
| `bad_enum` | `exit_state` is not in the allowed set. |
| `bad_hash_format` | `prompt_hash` does not match `sha256:[0-9a-f]{64}`. |
| `bad_iso8601` | `ts` does not parse as ISO-8601 with `Z`. |
| `negative_duration` | `tools_called[*].duration_ms` is negative. |
| `non_monotonic_step_index` | Per-mission `step_index` is out of order or has gaps. |
| `record_after_done` | A record exists for a mission already terminated by `done`. |

These codes are stable. Downstream tooling (CI gates, dashboards)
may match on them.
