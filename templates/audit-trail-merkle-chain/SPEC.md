# SPEC: audit-trail-merkle-chain

## File format

JSONL. One entry per line. Entries are appended; never edited;
never deleted.

## Entry shape

```json
{
  "index": 0,
  "ts": "<RFC3339 UTC>",
  "prev_hash": "<hex sha256 of the previous entry's canonical form, or 64×'0' for index 0>",
  "payload": { ... arbitrary caller-supplied JSON ... },
  "entry_hash": "<hex sha256 of canonical(entry_without_entry_hash)>"
}
```

Field semantics:

- `index` — strictly increasing, starts at 0, no gaps.
- `ts` — informational only; **not part of the integrity story**.
  Hashing covers `ts` because it sits inside the entry, but
  verification does not separately check ts monotonicity (clock
  skew is real). Use `index` for ordering.
- `prev_hash` — the prior entry's `entry_hash`, or 64 zeros for
  the genesis entry.
- `payload` — opaque to the chain. Caller is responsible for
  redaction *before* the entry is appended.
- `entry_hash` — covers everything in the entry except the
  `entry_hash` field itself.

## Canonicalization

```python
json.dumps(entry_without_entry_hash, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
```

Same canonical form as `idempotency-key-protocol`. Reuse if both
templates are in play.

## Append rules

1. Read the current last entry's `entry_hash` (or use 64 zeros if
   the file is empty / does not exist).
2. Build the new entry with `index = last_index + 1`,
   `prev_hash = last_entry_hash`, the supplied `payload`, and
   `ts = clock()`.
3. Compute `entry_hash` over the canonical form of the entry
   minus the `entry_hash` field.
4. Append the full JSON object as one line, terminated by `\n`.
5. fsync if durability matters at the entry level.

The append step is the only mutation allowed on the file. Any
process that opens it for write-other-than-append is a violation
of the protocol regardless of what the chain looks like.

## Verification rules

Walk the file front-to-back. For each entry at line `i`:

1. Parse JSON; reject malformed lines with index = i, error =
   `parse`.
2. Confirm `index == i`.
3. Confirm `prev_hash == prior_entry_hash` (or 64 zeros at i=0).
4. Recompute `entry_hash` over the canonical form of the entry
   minus the stored `entry_hash`. Confirm equality.
5. If an `expected_head_hash` is provided, confirm the final
   entry's `entry_hash` matches it after the walk completes.

Any mismatch terminates verification with a structured error:

```json
{
  "ok": false,
  "broken_at_index": 5,
  "reason": "entry_hash_mismatch" | "prev_hash_mismatch" | "index_gap" | "parse" | "head_mismatch",
  "detail": { ... }
}
```

A successful walk returns:

```json
{
  "ok": true,
  "entries_verified": 42,
  "head_hash": "<hex sha256>"
}
```

## Threat model

In scope:

- Single-byte edits anywhere in the file.
- Insertion or deletion of whole lines.
- Reordering of lines.
- Truncation (caught only if `expected_head_hash` is supplied).

Out of scope:

- An attacker who controls both the log file *and* the published
  head hash. The published head hash MUST live somewhere the
  attacker does not control, or the chain is theatre.
- Collision resistance failure of SHA-256.
- Side-channel leakage via `payload` content. That is the
  redaction template's job, not this one's.
