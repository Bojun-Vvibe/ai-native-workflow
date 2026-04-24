# Example 01 — clean log validates with zero errors

## What this shows

A four-step mission emits a well-formed decision log: one `continue`
per step, ending with a single `done`. Every record carries the
required eight fields, `step_index` is `0,1,2,3` per the monotonicity
rule, the `prompt_hash` values match the regex, and `ts` is ISO-8601
UTC. The validator exits 0 with `errors: []`.

## Run

```bash
python3 ../../bin/decision_log_validate.py decisions.jsonl
```

## Verified output

```json
{
  "errors": [],
  "input": "decisions.jsonl",
  "invalid_records": 0,
  "missions_completed": 1,
  "missions_seen": 1,
  "total_records": 4,
  "valid_records": 4
}
```

Exit code: `0`.

## What to read from this

- The validator is a CI gate: drop it into a job that runs
  `decision_log_validate.py path/to/log.jsonl` and the build fails
  on any non-conforming line.
- Optional fields like `tokens_in` / `tokens_out` are present on
  some records and absent on others — the validator ignores unknown
  and missing-optional fields. This is intentional so a richer
  schema can be adopted later without breaking older logs.
- The `done` on the final record is what counts the mission as
  completed in the report's `missions_completed` field.
