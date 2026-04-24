# Template: idempotency-key-protocol

A small convention + reference validator + replay test for making
agent tool calls **safely retryable**. Every tool invocation
carries an `Idempotency-Key` field. The tool host keeps a small
keyed ledger of completed calls. A retry with the same key returns
the **stored response** instead of re-executing the side effect.
A retry with the same key but a **different request body** is a
hard error — the agent has a bug, not a network blip.

This template is the side-effect counterpart to
`tool-call-retry-envelope`. The retry envelope handles "should I
retry"; this protocol handles "is it safe to retry". They compose:
the envelope decides timing, the protocol guarantees correctness.

## Why this exists

Three failure modes that show up the moment an agent loop has
non-trivial side effects (write a file, post a comment, charge a
card, create a branch, send a message):

1. **Double-write on transient failure.** The tool succeeded server
   side; the response packet was lost; the agent retries; the side
   effect happens twice. Two PR comments, two branches, two
   charges.
2. **Silent divergence under retry.** The agent retries with a
   "fresh" request body that includes a new timestamp or a freshly
   sampled prompt. The server treats the second call as a brand
   new operation. Idempotency was assumed but never enforced.
3. **Replay-as-denial-of-service.** Without dedupe, an agent stuck
   in a retry loop multiplies real work N× upstream. Rate limits
   and cost ceilings get blamed; the real cause is missing keys.

The protocol fixes all three with one rule: **identical key +
identical request body ⇒ stored response, no re-execution. Identical
key + different body ⇒ `IdempotencyConflict`.**

## When to use it

- Any tool whose call has external side effects (filesystem, network,
  billing, identity).
- Any agent loop wrapped in a retry envelope.
- Any cross-process handoff where the second process might re-issue
  a call from the first.

When *not* to use it:

- Pure read-only tools — overhead with no benefit.
- Side effects that are inherently idempotent at the destination
  (e.g. PUT-by-ID where the destination already dedupes). Still
  cheap to add, but optional.

## Files

- `SPEC.md` — the wire format and the three rules.
- `bin/idempotency_store.py` — stdlib-only reference store +
  validator. Keys are caller-provided; the store does not generate
  them. Clock and storage path are injected.
- `bin/replay_test.py` — a deterministic harness that exercises the
  three legal transitions (fresh / replay / conflict) and prints
  one line per transition.
- `examples/01-replay-deduped/` — happy path: a tool call retried
  three times runs once.
- `examples/02-conflict-detected/` — bug path: same key, different
  body, raises `IdempotencyConflict`.

## How keys are formed

Caller-provided. Recommended construction:

```
sha256(f"{agent_id}:{mission_id}:{step_id}:{tool_name}:{logical_op_id}")[:16]
```

The store does not enforce a construction — it only enforces that
the same key always maps to the same request body. The
recommendation matters because it makes keys **stable across
process restarts** (so a resumed agent dedupes against its own
prior work) and **scoped per logical operation** (so two distinct
"post comment" calls in the same step don't collide).

## TTL

Entries expire after a caller-supplied TTL (default 24h in the
reference store). Two reasons:

1. The ledger is unbounded otherwise.
2. After TTL, a "retry" is almost certainly a new logical
   operation that happens to reuse a key — treating it as a
   conflict would be more annoying than useful.

## See also

- `tool-call-retry-envelope` — pairs with this; supplies the
  retry policy.
- `tool-call-circuit-breaker` — orthogonal; trips on persistent
  tool failure regardless of idempotency.
- `partial-failure-aggregator` — collects per-key outcomes when
  fan-out tool calls each carry their own key.
