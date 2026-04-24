# ENVELOPE.md — wire-format spec

The retry envelope is a JSON object that wraps every tool-call
request and response. It is transport-agnostic (HTTP, WebSocket,
in-process function call, queue message — all work) and
SDK-agnostic.

## Request envelope

```json
{
  "tool_name": "stripe.charges.create",
  "arguments": {
    "amount": 1999,
    "currency": "usd",
    "customer": "cus_abc123",
    "description": "Order #4421"
  },
  "envelope": {
    "idempotency_key": "tcre_v1_8f3c2a91d4b6e0f7c5a8b2d1e9f4c6a7b3d8e1f9c2a5b4d6e8f1a3c7b9d2e4f6",
    "attempt_number": 1,
    "max_attempts": 4,
    "deadline": 1745557200000,
    "retry_class_hint": "first_attempt",
    "agent_session_id": "sess_4f1a8c",
    "tool_call_id": "call_2x9q4r"
  }
}
```

### Required fields

| Field | Type | Notes |
|---|---|---|
| `tool_name` | string | Fully-qualified tool identifier. Stable across versions of the same tool; if the wire-contract changes, the tool gets a new name. |
| `arguments` | object | Tool-specific. The host MAY canonicalise this before key derivation; the agent SHOULD NOT depend on argument-order stability for correctness. |
| `envelope.idempotency_key` | string | 256-bit hash, hex-encoded with `tcre_v1_` prefix. Length is fixed at 72 chars. Derived host-side per `bin/derive-key.py`. |
| `envelope.attempt_number` | integer ≥ 1 | Resets to 1 if `idempotency_key` changes. |
| `envelope.max_attempts` | integer ≥ 1 | Hard ceiling. The agent loop SHOULD NOT exceed this; the host MUST enforce it. |
| `envelope.deadline` | integer | Absolute Unix timestamp in milliseconds. The host MUST NOT execute the side effect after this. |
| `envelope.retry_class_hint` | enum | `first_attempt` \| `transport_blip` \| `agent_loop_retry` \| `payload_edited`. Advisory; the dedup table is authoritative. |

### Optional fields

| Field | Type | Notes |
|---|---|---|
| `envelope.agent_session_id` | string | Useful for log correlation. SHOULD be included in `scope` for key derivation. |
| `envelope.tool_call_id` | string | The SDK's per-call ID. Useful for tracing; NOT used for dedup (it changes on every retry). |
| `envelope.correlation_id` | string | End-to-end trace ID. Echoed in the response. |

### Forbidden fields

The envelope MUST NOT carry:

- Authentication tokens (those go in transport headers).
- Cleartext PII duplicated from `arguments` (those go through key
  derivation only).
- Free-form `notes` / `comments` (those break canonicalisation
  reasoning if anyone tries to dedup on them later).

## Response envelope

```json
{
  "result": {
    "id": "ch_3OkLqwHP2A0ZxR1z",
    "amount": 1999,
    "status": "succeeded"
  },
  "envelope": {
    "dedup_status": "executed_now",
    "original_attempt_number": 1,
    "executed_at": 1745557180123,
    "idempotency_key": "tcre_v1_8f3c...",
    "correlation_id": "trace_x7y9z2"
  }
}
```

### dedup_status values

| Value | Meaning | Agent-loop response |
|---|---|---|
| `executed_now` | This attempt performed the side effect. | Pass `result` to the model unchanged. |
| `replayed_from_cache` | A previous attempt did the work; this is the cached result. | Same as `executed_now` — model does not need to know. |
| `expired` | `deadline` passed before the host could act. Nothing happened. | Treat as failure. The model decides whether to call again with a new deadline. |
| `rejected_max_attempts` | `attempt_number > max_attempts`. | Hard fail. Bubble up to the human / orchestrator. |
| `rejected_key_collision` | Hash matched a row whose `identity_fields_canonical` disagreed. | Hard fail. This is almost always a host bug; alert loudly. |

## Key derivation rules

The host (not the agent, not the SDK) derives `idempotency_key` from:

```
idempotency_key = "tcre_v1_" + sha256_hex(
    canonical_json({
        "tool":      tool_name,
        "identity":  pick(arguments, IDENTITY_FIELDS[tool_name]),
        "scope":     {
            "tenant":  request.tenant_id,
            "session": envelope.agent_session_id
        }
    })
)
```

`IDENTITY_FIELDS` is a per-tool allowlist. Examples:

| Tool | IDENTITY_FIELDS |
|---|---|
| `email.send` | `["to", "subject_hash", "body_sha256"]` |
| `stripe.charges.create` | `["customer", "amount", "currency", "metadata.order_id"]` |
| `git.push` | `["remote_url", "branch", "commit_sha"]` |
| `db.execute` | `["statement_template", "param_hash"]` |

Three rules govern `IDENTITY_FIELDS`:

1. **Include every arg that, if changed, should produce a different
   side effect.** If editing `to_address` should send a second
   email, include `to`.
2. **Exclude every arg that is cosmetic or derived.** `request_id`,
   `timestamp`, `client_user_agent` — never identity.
3. **Hash large fields.** Don't put a 50KB email body in the key
   input; put `sha256(body)` in.

Misclassifying an `IDENTITY_FIELD` is the source of nearly every
silent dedup bug in this template's failure-mode catalog.

## Versioning

The `tcre_v1_` prefix on the key is part of the wire contract.
Bumping to `tcre_v2_` invalidates every cached row. Hosts SHOULD
keep the v1 prefix recogniser for at least one TTL window (default
24h) to drain in-flight retries.

## Backwards compatibility with envelope-unaware tools

A tool-host that does not understand the envelope MUST ignore the
`envelope` field and treat the call as a fresh execution every time.
This degrades to "no dedup" for that tool — the same situation you
have without the envelope. The agent loop SHOULD detect missing
`envelope` in the response and downgrade `dedup_status` reasoning
to "unknown" for that tool.
