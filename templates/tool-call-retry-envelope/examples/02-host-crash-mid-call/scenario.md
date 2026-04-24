# Example 02 — host crash mid-call

## Scenario

The agent calls `db.execute` to insert a new order row. The host:

1. Acquires a database connection.
2. Executes the `INSERT`. The row commits.
3. Writes the dedup-table row.
4. Receives `SIGKILL` from the platform's OOM-killer **before** it
   can serialise the response back to the agent.

The host process restarts. The dedup table is durable (it lives in
the same database as the orders table, in a transaction with the
order insert), so the row is intact. The agent loop, having seen the
WebSocket close with no reply, classifies the failure
`retry_safe` and re-issues with `attempt_number=2`.

## What the envelope guarantees

- The order row exists exactly once.
- Attempt 2 finds the dedup row, returns `replayed_from_cache`.
- The model sees the original insert's row ID, not a new one.

## Why the dedup write must be in the same transaction

If the dedup write is in a *separate* transaction, the host can crash
in a state where the order is committed but the dedup row is not. On
retry, the dedup table reports a miss, the host re-executes the
insert, and the order is duplicated. The reference SQL in
`contracts/dedup-table.sql` lives in the same database deliberately
so the host can wrap both writes in one transaction.

## How to run

```sh
cd templates/tool-call-retry-envelope/examples/02-host-crash-mid-call
python3 ../../bin/dedup-replay.py scenario.json
```

## Expected outcome

```
Step 1: executed_now_BUT_TRANSPORT_DROPPED   (host died after dedup write)
Step 2: replayed_from_cache                   (post-restart retry sees row)
Final dedup-table size: 1
```
