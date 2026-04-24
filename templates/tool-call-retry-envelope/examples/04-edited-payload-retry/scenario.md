# Example 04 — agent retries with edited payload

## Scenario

The agent calls `email.send` to notify Alice. Then the agent
realises the recipient should be Bob (e.g. the model corrected
itself, or the user said "wait, send it to Bob instead"). It
re-calls `email.send` with the **same body** but `to=bob@example.com`.

Because `to` is in the `IDENTITY_FIELDS` allowlist for `email.send`,
the host derives a **different** key for the second call. The dedup
table treats it as a fresh send.

## What the envelope guarantees

- Alice and Bob each get exactly one email.
- The host's dedup table has two rows, one per recipient.
- A retry of *either* call (e.g. transport blip on the Bob send)
  replays the correct cached result, not the other one.

## What this would look like without identityFields

If the host hashed the *entire* arguments object as the key, then:

- Same key for Alice and Bob? No — `to` differs, so the key changes.
  This case happens to work even with naive hashing.

If the host hashed the body alone (a common mistake):

- The Alice send and the Bob send would share a key.
- Bob's send would `replay_from_cache` the Alice result.
- Bob never receives the email.
- The agent reports success.

The `IDENTITY_FIELDS` allowlist makes this discipline explicit and
auditable: *exactly these fields determine identity, full stop.*

## How to run

```sh
cd templates/tool-call-retry-envelope/examples/04-edited-payload-retry
python3 ../../bin/dedup-replay.py scenario.json
```

## Expected outcome

```
Step 1: executed_now           (Alice send, msg_001, key A)
Step 2: executed_now           (Bob send,   msg_002, key B — different key!)
Final dedup-table size: 2
```

The two keys are different by construction:

- Key A: `tcre_v1_4aa4484c2eaba7cce4f28b670d5066df2adfec7e132cc1e22bc5b71051c5fca7`
- Key B: `tcre_v1_c0f1b6db72255906dcacb2e7d39653f4fea875dff4ac44f62a1d78c6c3291b5f`
