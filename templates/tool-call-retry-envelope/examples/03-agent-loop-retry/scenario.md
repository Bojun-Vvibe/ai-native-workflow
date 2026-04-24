# Example 03 — agent loop retry (model gives up waiting)

## Scenario

The agent calls `email.send` to notify Alice that her order shipped.
The host actually completes the send and writes the dedup row. Both
the side effect AND the transport succeed.

But the agent loop, distracted (e.g. cancelled the in-flight call
because of a concurrent tool resolution, or because the user
interrupted), decides it never saw a result. The model schedules a
fresh call to `email.send` with the **same** arguments and the loop
re-issues the envelope with `attempt_number=2` and
`retry_class_hint=agent_loop_retry`.

## What the envelope guarantees

- Alice gets exactly one email.
- Attempt 2 hits the dedup table on the same key (because identity
  fields — `to`, `subject_hash`, `body_sha256` — are unchanged).
- The model sees the original send's message-ID.

## Why this case is distinct from example 01

In example 01 the host knows the transport dropped (the SSE socket
closed); in example 03 the host has no idea anything went wrong on
its side — both side effect and transport succeeded. The dedup
contract handles both shapes the same way because it is keyed off
the *envelope*, not the connection.

## How to run

```sh
cd templates/tool-call-retry-envelope/examples/03-agent-loop-retry
python3 ../../bin/dedup-replay.py scenario.json
```

## Expected outcome

```
Step 1: executed_now            (email sent, msg_id_001)
Step 2: replayed_from_cache     (same key, attempt 2 returns msg_id_001)
Final dedup-table size: 1
```
