# Template: partial-failure aggregator

A pure aggregator that collapses N independent fan-out tool-call results
into ONE structured verdict the orchestrator can branch on:

- `verdict`: `all_ok` | `partial_ok` | `all_failed` | `quorum_ok` | `quorum_failed`
- `advice`: `proceed` | `proceed_degraded` | `retry_failed_only` | `abort`
- `ok_count` / `fail_count` / `skipped_count` / `total`
- `first_failure` (deterministic — first by input order)
- Full `by_id` map so callers can build a retry payload of just the failed ids

Stdlib-only. No I/O inside the aggregation function. CLI exits **0** for any
"proceed*" advice, **1** for `retry_failed_only`, **2** for `abort` — drops
straight into a shell `if/elif/else`.

## Why this exists

When an agent fans out K independent tool calls — parallel reads from K
shards, multi-region writes, multi-source RAG fetches, K concurrent search
queries — the orchestrator has to make ONE next decision. Two ad-hoc patterns
that both lose information:

1. **`all(ok)` short-circuit.** Throws away the K-1 successes the moment one
   call fails. Caller has no idea whether to retry one call or the whole
   batch.
2. **Raise on first failure.** Same problem, plus it racy-cancels in-flight
   work that may have already succeeded.

This template gives you a *named* verdict and an *advice* string so every
mission's branching is uniform, replayable, and grep-able in a decision log.

## When to use this

- Multi-source RAG fetch where 4-of-5 results is good enough.
- Multi-region writes where you need a quorum.
- Parallel scout investigations where one failed scout shouldn't kill the
  mission but two should.
- Any fan-out where the orchestrator's next action depends on *how many*
  succeeded, not just *whether all* succeeded.

## When NOT to use this

- Sequential, dependent calls — use plain control flow, not an aggregator.
- Single-call retry — use `tool-call-retry-envelope` instead.
- Long-running streaming aggregations — this is a one-shot collapse, not a
  reducer over time.
- When you need cost/health gating per call — pair with
  `tool-call-circuit-breaker` and `agent-cost-budget-envelope` (those decide
  *whether* to make the call; this one decides *what to do after* the batch).

## Design

### Inputs

`policy` — small dict, validated:
```json
{
  "mode": "all" | "quorum",
  "quorum": 2,                            // required iff mode=="quorum"
  "skipped_counts_as": "ok" | "fail" | "ignore"   // default "ignore"
}
```

`results` — list of dicts, each:
```json
{"id": "<unique string>", "status": "ok"|"error"|"timeout"|"skipped",
 "error_class": "<optional string>"}
```

Validation is strict: missing/duplicate ids, bad statuses, missing `quorum`
all raise `ValueError`. The aggregator never silently drops a result.

### Verdict matrix

| mode | conditions | verdict |
|---|---|---|
| `all` | `total == 0` | `all_failed` |
| `all` | `fail == 0 and ok == total` | `all_ok` |
| `all` | `ok == 0` | `all_failed` |
| `all` | otherwise | `partial_ok` |
| `quorum` | `ok >= quorum` | `quorum_ok` |
| `quorum` | `ok < quorum` | `quorum_failed` |

`skipped_counts_as` is applied **before** counting, so a `skipped` result
with `skipped_counts_as=fail` is what trips a `quorum_failed`.

### Advice mapping

| verdict | fail_count | advice |
|---|---|---|
| `all_ok` | 0 | `proceed` |
| `quorum_ok` | 0 | `proceed` |
| `quorum_ok` | >0 | `proceed_degraded` |
| `partial_ok` | * | `retry_failed_only` |
| `all_failed` / `quorum_failed` | * | `abort` |

### Determinism

- `by_id` preserves input order (insertion-ordered dict).
- `first_failure` is the first failing result by input order, not
  lexicographic id.
- The function is a pure transform: same `(policy, results)` → byte-identical
  JSON output.

## Layout

```
templates/partial-failure-aggregator/
├── README.md
├── bin/
│   └── aggregate.py          # pure function + CLI; no deps
└── examples/
    ├── 01-mixed-fanout/      # 3-of-5 ok, mode=all, advice=retry_failed_only
    └── 02-all-fail-with-quorum/   # 0-of-3 ok, mode=quorum/2, advice=abort
```

## Worked example 1 — mixed fan-out, retry the failed two

5 parallel repo searches; 3 succeed, 2 fail (one timeout, one rate-limited).
Policy is `mode=all`, so the verdict is `partial_ok` and the advice tells the
orchestrator to retry only `search-repo-c` and `search-repo-e`.

```bash
./bin/aggregate.py examples/01-mixed-fanout/policy.json \
                   examples/01-mixed-fanout/results.json
```

Verified stdout (exit code **1** = retry):

```json
{
  "verdict": "partial_ok",
  "ok_count": 3,
  "fail_count": 2,
  "skipped_count": 0,
  "total": 5,
  "policy": {
    "mode": "all",
    "skipped_counts_as": "ignore"
  },
  "by_id": {
    "search-repo-a": {"status": "ok", "error_class": null},
    "search-repo-b": {"status": "ok", "error_class": null},
    "search-repo-c": {"status": "timeout", "error_class": "deadline_exceeded"},
    "search-repo-d": {"status": "ok", "error_class": null},
    "search-repo-e": {"status": "error", "error_class": "rate_limited"}
  },
  "first_failure": {
    "id": "search-repo-c",
    "status": "timeout",
    "error_class": "deadline_exceeded"
  },
  "advice": "retry_failed_only"
}
```

The orchestrator's branch is now trivial:

```bash
case $? in
  0) echo "proceed" ;;
  1) retry_ids=$(jq -r '.by_id | to_entries | map(select(.value.status!="ok"))[].key' verdict.json) ;;
  2) abort_mission ;;
esac
```

## Worked example 2 — quorum fail with `skipped_counts_as=fail`

3 multi-region writes. Two error/timeout, one was preflight-denied and never
ran. Policy requires a quorum of 2 oks, and `skipped_counts_as=fail` means
the preflight-denied region is treated as a failure for quorum math (so a
silent skip can't pass a quorum check).

```bash
./bin/aggregate.py examples/02-all-fail-with-quorum/policy.json \
                   examples/02-all-fail-with-quorum/results.json
```

Verified stdout (exit code **2** = abort):

```json
{
  "verdict": "quorum_failed",
  "ok_count": 0,
  "fail_count": 3,
  "skipped_count": 0,
  "total": 3,
  "policy": {
    "mode": "quorum",
    "quorum": 2,
    "skipped_counts_as": "fail"
  },
  "by_id": {
    "region-us-east": {"status": "error", "error_class": "5xx"},
    "region-us-west": {"status": "timeout", "error_class": "deadline_exceeded"},
    "region-eu-west": {"status": "skipped", "error_class": "preflight_denied"}
  },
  "first_failure": {
    "id": "region-us-east",
    "status": "error",
    "error_class": "5xx"
  },
  "advice": "abort"
}
```

Note `skipped_count: 0` even though one input was `skipped` — that's because
`skipped_counts_as=fail` reclassifies it for both counters and the verdict.
The original status is still preserved verbatim in `by_id` so the decision
log shows the truth.

## Composes with

- **`tool-call-retry-envelope`** — the `retry_failed_only` advice gives you
  the exact set of ids to re-issue under the retry envelope.
- **`agent-decision-log-format`** — append the verdict + advice as a single
  decision-log line so a mission replay can rebuild the branch taken.
- **`tool-call-circuit-breaker`** / **`agent-cost-budget-envelope`** — those
  gate individual calls before they happen; this aggregator gates the
  orchestrator's *next step* after the batch returns.
