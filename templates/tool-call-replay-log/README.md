# tool-call-replay-log

Append-only, fingerprinted log of every tool call (request **and** response) an agent issues, designed to make a non-deterministic agent session **deterministically replayable** offline. The log is the single source of truth for "what did the agent actually see at the moment it made decision X" — it is the artifact you reach for when a production trace looks wrong, when a reviewer asks "would the same prompt have produced the same call?", and when a regression suite needs to compare today's behaviour against last week's without re-hitting any external service.

## The pattern

A `ReplayLog(path)` wraps a JSONL file with three operations:

- `record_call(tool, args, result, *, status, started_at, finished_at, attempt_id)` — atomically appends one record. The file is opened `O_APPEND` per write, so two concurrent writers interleave at line boundaries (POSIX guarantees `write(2)` ≤ `PIPE_BUF` is atomic, and JSONL rows are well below that for typical tool I/O). Every record carries a `prev_hash` linking back to the previous record's `record_hash`, forming a tamper-evident chain. The first record's `prev_hash` is the empty-string SHA-256 sentinel `e3b0c44...`.
- `replay(tool, args)` — returns the next not-yet-consumed result for `(tool, canonical(args))` from the log, in the order it was originally recorded. Multiple calls with the same key return successive results, never the same one twice. Misses raise `ReplayMiss` so a drifted prompt cannot silently fall back to a stale response.
- `verify()` — re-walks the chain and returns `(records_checked, ok)`. A single missing or modified byte breaks the chain and `ok=False` is returned with the offending sequence number.

Argument canonicalization is the same rule used elsewhere in this catalog: sorted keys, no whitespace, floats raise `CanonicalizationError` with a JSON pointer to the offending field. This makes the cache key independent of dict iteration order and forbids the silent precision loss that `0.1 + 0.2` introduces. Identity-arg allowlists are caller-declared per tool so volatile metadata (request-ids, server timestamps, retry counters) does not defeat replay.

## When to use it

- **Post-mortem of a single bad agent run.** Capture the log in production, copy it to your laptop, replay against the same prompt with `OPENAI_API_KEY=invalid` set; every tool the agent calls returns the recorded result and you can step through decisions without paying or waiting.
- **Regression-testing a prompt change.** Record one canonical run, then for every PR re-run the agent with the log mounted in replay mode and diff the resulting transcript. A behavioural drift surfaces as a `ReplayMiss` on the first call that no longer matches.
- **Cheap eval against a frozen world.** A live tool surface (`web_fetch`, `read_clock`, `list_files`) is the enemy of reproducibility. Recording one good run lets you replay it 1000× during prompt iteration without flapping.
- **Forensic audit.** The hash chain detects after-the-fact tampering of a recorded session (a reviewer adding a fake "the agent did consult policy X" line into yesterday's log).

## When NOT to use it

- **As a result cache.** A cache lives forever, replay consumes results in order. If your goal is "skip the upstream call when args match," use `tool-result-cache` (with explicit `safe_tools` and `ttl_s`). Replaying a `POST /charge` against a recorded success is not skipping a call — it is **lying** about a side effect.
- **For non-deterministic agents whose tool order itself is random.** Replay assumes the same prompt produces the same tool sequence. If your agent samples `temperature=0.7` and asks tools in a different order on the second run, every call past the divergence point misses. Pin the model, pin the seed, then record.
- **Across schema changes.** A log recorded against `read_file(path)` cannot replay a new agent that calls `read_file(path, encoding=...)` — the canonical key differs and replay misses (correctly!). Plan to re-record on every tool-surface change.
- **For huge binary results.** JSONL is fine for kilobytes; for megabyte-scale results record a content-addressed pointer and store the bytes in a sibling object store.

## Alternatives and how they differ

- **`tool-result-cache`** — long-lived, TTL'd, key-addressed, *idempotent on read*. A cache hit returns the same result every time. Replay returns one recorded occurrence per call.
- **`tool-call-deduplication`** — collapses an agent's same-tick re-issues of the same call into one execution. Deals with thought loops, not with reproducing yesterday's session.
- **`request-coalescer`** — collapses N concurrent in-flight identical calls into one. In-flight only; no persistence; no replay.
- **`audit-trail-merkle-chain`** — full Merkle tree for cryptographic non-repudiation across many actors. Replay log is a single-actor, single-session linear chain — much cheaper, much narrower.
- **`agent-decision-log-format`** — human-readable per-decision JSONL for analysts. Replay log is machine-fed back into the agent; the two compose well (one trace, two consumers).

## Composition

The replay log sits **outside** the dedup/cache/coalescer stack. A typical pipeline in record mode is `agent → coalescer → dedup → cache → tool → replay-log.record_call(...) → return`. In replay mode the cache and coalescer are bypassed entirely and `replay()` short-circuits at the bottom of the stack. Pair with `prompt-fingerprinting` so a recorded log carries the prompt hash that produced it; replaying against a different fingerprint should warn loudly.

## Failure modes the implementation defends against

1. **Mid-write crash.** Each record is one `write()` of `len(line) ≤ PIPE_BUF`; a crash either commits a whole record or none. `verify()` truncates a torn trailing line cleanly and reports it.
2. **Concurrent writers.** `O_APPEND` per write linearizes appends across processes on a single host. Cross-host concurrent writers are out of scope — record from one process at a time.
3. **Replay drift.** Argument canonicalization removes dict-order and whitespace as failure sources; the identity-arg allowlist removes volatile metadata. A genuine prompt change still misses (the desired behaviour).
4. **Tampering.** The `prev_hash` chain detects insertion, deletion, or modification of any record; `verify()` returns the first bad seq so the operator can isolate the corruption.

## Files in this template

- `replay_log.py` — stdlib-only reference implementation (≈170 lines).
- `example.py` — five-part worked example: record three calls, verify the chain, replay them in order, prove a `ReplayMiss` on a drifted arg, and prove tamper detection via `verify()`.
