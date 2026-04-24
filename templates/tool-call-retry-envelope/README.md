# Template: tool-call-retry-envelope

A wire-format and host-side dedup contract for making agent tool
calls **safely retryable** without the host re-executing the side
effect, and without the agent having to invent a fresh idempotency
discipline at every call site.

This template is the operational counterpart to the long-form post
on host-derived semantic-hash idempotency keys. The post argues for
a particular *key derivation strategy*; this template specifies the
*envelope* that carries the key, the *host-side dedup table* that
honours it, and the *retry-classification* the agent loop is allowed
to apply on top.

## Why this exists

Three things are true at once in any agent → tool → external-effect
loop:

1. **The transport will fail.** SSE streams die, HTTP/2 frames stall,
   the WebSocket reconnects mid-response, the tool-host process
   crashes after the side effect but before the JSON reply gets back.
2. **The agent loop will retry.** Either implicitly (the SDK's
   built-in retry) or explicitly (the model decides to call the same
   tool again because it didn't see a result). Frequently both.
3. **The user does not want the side effect to happen twice.** Two
   payments. Two emails. Two `git push`es. Two rows.

If the tool-host has no idempotency contract, every retry is a
50/50 coin flip on whether the user gets billed twice. If the
*envelope* carrying the call has no dedicated retry fields, every
host has to reverse-engineer "is this a retry?" from headers, body
shape, or worse — timing.

This template fixes that with one envelope, one dedup-table contract,
and one retry classifier the agent loop can lean on.

## What's in the box

```
tool-call-retry-envelope/
├── README.md                              # this file
├── ENVELOPE.md                            # wire-format spec + field semantics
├── contracts/
│   ├── envelope.schema.json               # JSON Schema for the request envelope
│   ├── response.schema.json               # JSON Schema for the response envelope
│   └── dedup-table.sql                    # reference SQLite schema for the host
├── bin/
│   ├── derive-key.py                      # host-side semantic-hash key derivation
│   ├── classify-retry.py                  # given a failure, decide retry-class
│   └── dedup-replay.py                    # CLI that simulates dedup table behaviour
├── prompts/
│   └── retry-decision.md                  # strict-JSON prompt: should the agent retry?
└── examples/
    ├── 01-network-blip/                   # SSE drops mid-stream after side effect
    ├── 02-host-crash-mid-call/            # tool-host SIGKILL between effect and reply
    ├── 03-agent-loop-retry/               # agent loop re-calls because no result seen
    └── 04-edited-payload-retry/           # agent retries with a *modified* payload
```

## When to use this template

Use it for any tool whose call has at least one of:

- **External side effect** that costs money, sends a message, or
  mutates a remote resource (`stripe.charges.create`, `slack.send`,
  `github.create_pr`, `db.execute INSERT`, `git.push`, `email.send`).
- **Non-idempotent local effect** (file rename, bump-counter,
  enqueue-once, schedule-once).
- **Long-running** (> ~5s) such that mid-call transport failures
  are routine.

Do **not** use it for:

- **Pure-read tools** (`http.get`, `kv.get`, `fs.read`). Retries
  there are free; an envelope is overhead.
- **Cheap, naturally idempotent local effects**
  (`logger.info`, `cache.set` with last-write-wins). Use it if you
  ever start charging for the call, but not before.
- **Streaming effects you cannot rewind** (audio output, websocket
  broadcast). Those need a different pattern (resumable cursors),
  not this one.

## The five fields the envelope adds

Every tool-call request carries five extra fields beyond
`tool_name` and `arguments`:

| Field | Purpose |
|---|---|
| `idempotency_key` | A 256-bit semantic hash derived host-side from `tool_name + canonical(arguments restricted to identityFields) + scope`. Stable across retries; changes if the agent edits a meaningful arg. |
| `attempt_number` | Monotone integer starting at 1. Incremented by the agent loop on every retry of the *same* logical call. Resets to 1 if `idempotency_key` changes. |
| `max_attempts` | Hard ceiling, e.g. 4. The host may refuse calls past this. |
| `deadline` | Absolute Unix timestamp (ms). The host must not perform the side effect past this; on expiry it returns `expired` not `success`. |
| `retry_class_hint` | Agent's claimed reason for the retry. Enum: `transport_blip`, `agent_loop_retry`, `payload_edited`, `first_attempt`. Advisory only — the host's own dedup table is authoritative. |

The matching response envelope adds:

| Field | Purpose |
|---|---|
| `dedup_status` | `executed_now` (this attempt did the side effect), `replayed_from_cache` (a previous attempt did it; this returns the cached result), `expired` (deadline passed; nothing happened), `rejected_max_attempts` (over the ceiling), `rejected_key_collision` (key matches but identityFields disagree — almost always a host bug or hash truncation). |
| `original_attempt_number` | If `replayed_from_cache`, which attempt actually ran. |
| `executed_at` | Server timestamp of the original execution. |

## How the host honours the envelope

A reference dedup table (see `contracts/dedup-table.sql`) is the
minimum the host needs:

```sql
CREATE TABLE tool_call_dedup (
  idempotency_key TEXT PRIMARY KEY,
  tool_name TEXT NOT NULL,
  identity_fields_canonical TEXT NOT NULL,  -- to detect key collisions
  result_json TEXT NOT NULL,
  executed_at INTEGER NOT NULL,
  attempt_number INTEGER NOT NULL,
  expires_at INTEGER NOT NULL               -- TTL: cache results for ~24h
);
```

The host's request flow:

1. Look up `idempotency_key`.
2. **Hit, identity_fields match** → return cached result with
   `dedup_status=replayed_from_cache`. Do **not** re-execute.
3. **Hit, identity_fields differ** → return
   `rejected_key_collision`. (Either host's hash is too short, or
   `identityFields` are misconfigured. Loud error.)
4. **Miss, deadline already passed** → return `expired` without
   executing.
5. **Miss, attempt_number > max_attempts** → return
   `rejected_max_attempts`.
6. **Miss, all OK** → execute the side effect, write result with
   `attempt_number`, return `executed_now`.

## How the agent loop classifies retries

The classifier (`bin/classify-retry.py`) takes a failure and emits
one of:

- `retry_safe` — transport-layer failure (network reset, 502/503/504,
  HTTP/2 GOAWAY, SSE drop). Same envelope, `attempt_number+1`,
  `retry_class_hint=transport_blip`.
- `retry_unsafe` — the host actively rejected the call
  (`401`, `403`, `400`, `rejected_*` from envelope). Do not retry;
  surface to the model.
- `retry_with_backoff` — `429`, `503 Retry-After`, `expired`. Wait
  the indicated backoff, then `retry_safe`-style retry.
- `do_not_retry` — the agent loop already retried the human-visible
  way (the model called the tool again). The new call has either the
  same or a different key; the dedup table will handle it.

The decision lives in the agent loop, not in the host, because only
the agent loop knows whether the model has "given up" and moved on
to a different tool.

## Six failure modes this prevents

1. **Double charges.** Without an envelope, an SSE drop after
   `stripe.charges.create` returns 200 leads to a retry that
   creates a second charge. With the envelope, attempt 2 hits the
   dedup table and replays the original receipt.
2. **Phantom orders.** The tool-host crashes after writing the row
   but before flushing the response. On restart, the agent retries.
   The dedup table has the row, replays the cached result, no
   duplicate.
3. **Edited-payload silent dedup.** The agent edits a `to_address`
   and retries. Without `identityFields`, a body-hash key would
   change and the email sends to two addresses. With `identityFields`
   restricted to the canonical recipient set, the key changes only
   when the recipient *intentionally* changes; an edit to the body
   alone reuses the key and replays — which is usually what the user
   wants.
4. **Retry storms past intent.** Without `max_attempts`, an agent
   loop in a tight retry can pound the host. The envelope caps it
   structurally.
5. **Stale retries.** Without `deadline`, a retry that arrives
   four hours late (because the agent paused to await a human) can
   still execute, often after the underlying intent has changed.
   The deadline shuts that down.
6. **Cross-tenant key collisions.** If two tenants both call
   `email.send` to the same `to_address`, naive content-hash keys
   collide. The host's `scope` injection (tenant ID, session ID,
   wallet ID) into the key derivation prevents this; the
   `rejected_key_collision` response makes hash misconfiguration
   loud rather than silent.

## Worked examples

Each example ships a `scenario.md`, the request/response envelopes
that flow during the failure, and the dedup-table state before/after.
All four use `bin/dedup-replay.py` so you can re-run them and verify
the outcomes deterministically.

| Example | Failure | Outcome |
|---|---|---|
| `01-network-blip` | SSE stream drops after side effect, before reply. | Attempt 2 → `replayed_from_cache`. Zero duplicate charges. |
| `02-host-crash-mid-call` | Tool-host SIGKILL after DB write, before HTTP response. | After restart, attempt 2 finds the row in dedup table → `replayed_from_cache`. |
| `03-agent-loop-retry` | Agent decides "no result, call again" with same args. | Same key, attempt 2 → `replayed_from_cache`. Model gets the original result. |
| `04-edited-payload-retry` | Agent edits `recipient`, retries. | Different `identityFields` → different key → `executed_now`. New row. Old row also retained. |

Run any of them:

```sh
cd templates/tool-call-retry-envelope/examples/01-network-blip
python3 ../../bin/dedup-replay.py scenario.json
```

## Adapt this section

Edit these to fit your stack:

- `contracts/envelope.schema.json` — add transport-specific fields
  your hosts need (e.g. `tenant_id`, `correlation_id`).
- `contracts/dedup-table.sql` — swap SQLite for whichever durable
  store the tool-host already uses. The table is the contract; the
  storage is implementation.
- `bin/derive-key.py` — adjust the `IDENTITY_FIELDS` map per tool.
  The default illustrates `email.send`, `stripe.charges.create`, and
  `git.push`.
- `bin/classify-retry.py` — extend the failure-class table with
  whatever exception types your transport raises.
- `prompts/retry-decision.md` — wire the strict-JSON output into
  whichever agent loop / SDK you run.

## When this template is overkill

For an agent loop that touches *only* read-only tools, skip this
entirely. The cost is real: every tool-host has to maintain a dedup
table, every call carries five extra fields, every developer has to
think about `identityFields`. Pay it for the calls that move money,
send messages, or mutate remote resources. Don't pay it for
`http.get`.

## Composes with

- `templates/agent-handoff-protocol/` — the `done` envelope can
  carry the `dedup_status` so the orchestrator can tell apart a
  "did the work" return from a "replayed from cache" return.
- `templates/agent-output-validation/` — validate that returned
  envelopes conform to `response.schema.json` before passing them
  back to the model.
- `templates/failure-mode-catalog/` — the failure modes prevented
  here are formalisations of "Phantom Effect" and "Edited-Payload
  Silent Dedup" entries in the catalog.

## License

MIT (see repo root).
