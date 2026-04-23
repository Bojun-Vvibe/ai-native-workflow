# Log-symptoms reference

The fastest path from a failed run to a named failure mode is
greppable log symptoms. This file lists what to grep / look for in
your agent logs and ledger to recognize each FM.

| FM ID | What to look for in logs |
|-------|--------------------------|
| FM-01 | `tool_calls` and `tokens_in` per turn rising monotonically; same files re-read across many turns |
| FM-02 | `tool_calls > 8` sustained for ≥3 consecutive turns with no `write`/`edit` between them |
| FM-03 | `KeyError`, `jsonschema.ValidationError`, "additional properties not allowed" |
| FM-04 | First plan emitted on turn 1–2; plan text never substantially edited; final summary uses identical wording to plan |
| FM-05 | `cache_hit_rate` dropped >0.3 from rolling 7-day baseline; first-turn token-in jump |
| FM-06 | `bridge-search.sh <symbol>` returns results in repos the agent didn't open; CI fails after merge in a sibling repo |
| FM-07 | `git rev-list --count main..upstream/main > 100`; PR fails to apply on upstream |
| FM-08 | ≥3 ledger entries with `parent_task_id == X` and matching `context_pointers` arrays |
| FM-09 | Provider invoice request count > local ledger count; intermittent latency >2× normal |
| FM-10 | Agent text contains a file path or function name with no preceding `read`/`grep` tool call for it |
| FM-11 | Edit tool call's `old` string fails to match (recovered via retry); `git diff` doesn't match agent's claimed sequence |
| FM-12 | `JSONDecodeError: Expecting value: line 1 column 1`; sub-agent output starts with ``` ``` ``` |

## Suggested grep one-liners

```bash
# FM-03 / FM-12 — sub-agent output parse failures
grep -E "JSONDecodeError|jsonschema.ValidationError|additional properties" agent.log

# FM-05 — cache regression
jq '[.cache_read, .cache_read + .fresh_input] | .[0]/.[1]' ledger.jsonl | \
  awk 'BEGIN{a=0;n=0} {a+=$1; n++} END{print "avg cache_hit_rate:", a/n}'

# FM-08 — continuation loop
jq -r 'select(.parent_task_id) | .parent_task_id' ledger.jsonl | sort | uniq -c | awk '$1>=3'

# FM-11 — edit retries
grep -c "edit tool: old string not found, retrying" agent.log
```

These are starting points. Adapt to your actual log format. The
goal is: every operator can run the right grep within 10 seconds
of opening a failed run.
