-- Reference dedup-table schema for the Tool-Call Retry Envelope.
-- This is the contract; the storage engine is up to the host.
-- Swap SQLite for Postgres / DynamoDB / Redis as appropriate.

CREATE TABLE IF NOT EXISTS tool_call_dedup (
    -- 256-bit semantic hash, hex-encoded with `tcre_v1_` prefix.
    -- Length is fixed at 72 chars; unique by construction.
    idempotency_key TEXT PRIMARY KEY,

    -- Tool that was called. Useful for debugging key collisions.
    tool_name TEXT NOT NULL,

    -- Canonical-JSON of the identityFields slice that produced the
    -- key. Used to *detect* hash collisions: if a request comes in
    -- with the same key but a different identity_fields_canonical,
    -- the host returns `rejected_key_collision`.
    identity_fields_canonical TEXT NOT NULL,

    -- The actual result that was returned to the agent. JSON.
    -- On replay, this is what the host returns verbatim.
    result_json TEXT NOT NULL,

    -- Server-side timestamp of the original execution (ms).
    executed_at INTEGER NOT NULL,

    -- attempt_number from the request that did the work.
    -- Replays return this in `original_attempt_number`.
    attempt_number INTEGER NOT NULL,

    -- TTL: when may this row be GC'd? Default 24h after executed_at.
    -- A retry that arrives after expires_at will see no row and
    -- re-execute — which is usually wrong; pick TTL > worst-case
    -- agent retry horizon.
    expires_at INTEGER NOT NULL,

    -- Optional: session that owned the call. Useful for debugging
    -- and for `scope`-based key derivation.
    agent_session_id TEXT
);

-- Index for GC sweeps.
CREATE INDEX IF NOT EXISTS idx_tool_call_dedup_expires
    ON tool_call_dedup (expires_at);

-- Index for per-tool debugging ("show me every replay of
-- stripe.charges.create in the last hour").
CREATE INDEX IF NOT EXISTS idx_tool_call_dedup_tool_executed
    ON tool_call_dedup (tool_name, executed_at);

-- Recommended GC: every 1h, run
--   DELETE FROM tool_call_dedup WHERE expires_at < ?;
-- with `?` = unix_ms_now(). Do not GC mid-call; serialise GC vs
-- request handling on the same key with row-level locking or a
-- single-writer GC worker.
