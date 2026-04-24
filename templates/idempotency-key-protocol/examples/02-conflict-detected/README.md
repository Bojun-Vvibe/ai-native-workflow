# Example 02 — conflict detected

A `send_message` tool is called once with body v1. The agent
re-issues the same idempotency key but, due to a bug, regenerates
the message text (body v2). The protocol refuses the second call
and surfaces the bug instead of silently sending a divergent
message.

## Run

```
python3 run.py
```

## Actual stdout

```
first_call status=fresh message_id=m-1
second_call status=conflict expected_hash=003226859a2338dd received_hash=3a0cfbbdf1758890
side_effects_total=1 (would have been 2 without the protocol)
```

## What to notice

- The first call goes through normally (`status=fresh`).
- The second call raises `IdempotencyConflict`. The agent should
  treat this as an unrecoverable bug — keys are supposed to bind
  to a specific request body. A different body under the same key
  means key construction is broken or request determinism is
  broken.
- Total real side effects = 1. Without the protocol it would have
  been 2 (a contradictory message would have been sent).
- This is the "loud failure" case the protocol is designed to
  produce. Silent divergence is the worst outcome; this is the
  next-best.
