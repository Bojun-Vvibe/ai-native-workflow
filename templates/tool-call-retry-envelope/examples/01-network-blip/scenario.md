# Example 01 — network blip mid-stream

## Scenario

The agent calls `stripe.charges.create` for $19.99 on a real
customer. The host:

1. Validates the call.
2. Charges the card (Stripe returns `ch_3OkLqwHP2A0ZxR1z`).
3. Writes the row to its dedup table.
4. Begins streaming the response back over SSE.

Halfway through the SSE stream, the customer's flaky office Wi-Fi
drops the connection. The agent loop sees a `RemoteProtocolError`
and classifies it `retry_safe`. It re-issues the **same** envelope
with `attempt_number=2` and `retry_class_hint=transport_blip`.

## What the envelope guarantees

- The card is charged exactly once.
- Attempt 2 hits the dedup table and replays the cached
  `ch_3OkLqwHP2A0ZxR1z` result.
- The model receives the same charge ID it would have seen if the
  network had not dropped.

## How to run

```sh
cd templates/tool-call-retry-envelope/examples/01-network-blip
python3 ../../bin/dedup-replay.py scenario.json
```

## Expected outcome

```
Step 1: executed_now_BUT_TRANSPORT_DROPPED  (row written, agent doesn't see result)
Step 2: replayed_from_cache                  (same key, attempt 2)
Final dedup-table size: 1
```

If the side effect ran twice the table would still have one row but
attempt 1 would show `executed_now` instead of `executed_now_BUT_TRANSPORT_DROPPED`,
and the customer would have been charged twice. The simulator
specifically models the "row written, transport dropped" sequence
because that is the real-world failure shape.
