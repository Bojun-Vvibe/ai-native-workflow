# `partial-output-checkpointer`

Periodic, byte-level checkpoint of streaming output so a kill
mid-flight leaves recoverable state. Append-only JSONL log of
flush boundaries, each carrying `bytes_committed` and a running
SHA-256, so recovery is "seek to `bytes_committed`, verify the hash
matches, resume from there."

Use cases:

- An LLM is streaming a 200KB structured response and the host gets
  OOM-killed at 140KB. Resume from the last checkpoint instead of
  re-burning the prompt.
- A tool is rendering a multi-megabyte report or PDF as a byte stream.
  A SIGTERM should leave a partially-good file on disk, not garbage.
- A long-running mission writes its decision log; a power loss should
  invalidate at most one trailing record, not the whole log.

This template is the *byte-stream* sibling of
`agent-checkpoint-resume` (which checkpoints discrete agent steps).
Use one or the other depending on whether your unit of progress is a
step boundary or a byte boundary.

## Why "torn trailing record" is a first-class concept

If the host dies mid-flush, the last line of the JSONL log will be
truncated — invalid JSON, possibly missing the trailing newline.
Three wrong responses are common:

1. **Crash on read** — the recovery code raises and the operator can't
   resume at all.
2. **Silently treat as success** — the half-written record is parsed
   loosely and a fictitious `bytes_committed` is reported, leading to
   a corrupt resume.
3. **Treat *any* parse failure anywhere as torn** — a corrupt
   *middle* record (real disk damage) is silently skipped, hiding an
   integrity problem.

The right answer, baked into `recover()`:

- A parse failure on the **trailing** line is treated as a torn write,
  reported as `torn_trailing_record=True`, and the resume point comes
  from the previous good record.
- A parse failure on **any other line** raises `CheckpointError` and
  the operator must investigate. The log is untrustworthy and silent
  recovery is the wrong default.
- Sequence numbers must be dense from 0; a gap also raises.

## SPEC

### `FlushPolicy(every_bytes, every_seconds)`

Both must be `> 0`. Flush fires when **either** threshold is met (the
classic "size or time, whichever first" rule). An empty buffer never
flushes — a quiet stream produces no spurious checkpoints.

### `Checkpointer(stream_id, policy, sink_write, log_write, now_fn)`

Inject the durable byte sink (`sink_write`) and the JSONL log appender
(`log_write`) — the engine itself does no I/O. `now_fn` is the clock.

| Method | Behavior |
|---|---|
| `append(chunk: bytes) -> int` | Buffer chunk; return 1 if a flush fired, 0 otherwise. Raises if called after `finalize`. |
| `finalize() -> dict` | Final flush (always emitted, marked `reason="finalize"`). Returns the run summary. Idempotent guard — second call raises. |
| `state() -> dict` | `{stream_id, bytes_buffered, bytes_committed, checkpoints, finalized}`. |

### Each log record

```json
{"stream_id":"...","seq":N,"bytes_committed":B,"chunk_bytes":C,
 "running_sha256":"...","flushed_at":T,"reason":"policy|finalize"}
```

`running_sha256` is over **all bytes written so far**, not just this
chunk, so recovery can verify the on-disk prefix in one pass.

### `recover(log_text, expected_stream_id=None) -> RecoveryPlan`

Parses the log and returns:

```python
RecoveryPlan(
    stream_id=...,
    bytes_committed=B,           # seek to this offset on the sink
    last_running_sha256=H,       # verify sha256(sink[:B]) == H
    intact_records=N,
    torn_trailing_record=bool,
)
```

If `expected_stream_id` is given and any record disagrees, raises
`CheckpointError` (mixed logs are a programmer error, not a recovery
case).

## Invariants

1. `bytes_committed` in the log monotonically increases by exactly
   `chunk_bytes` per record.
2. `running_sha256` of record N equals `sha256(sink[:bytes_committed])`
   at the moment of that flush.
3. A torn write is only tolerated on the **trailing** line.
4. `seq` is dense from 0; any gap raises.
5. `append` after `finalize` raises.
6. Empty buffer never produces a policy-flush record.

## Files

- `checkpointer.py` — pure stdlib reference engine + `recover()`.
- `example.py` — five-part worked example covering normal flow, torn
  trailing recovery, clean recovery, corrupt-middle rejection, and
  append-after-finalize.
- `expected_output.txt` — captured stdout (also pasted below).

## Worked example output — `example.py`

```
== part 1: stream 1200 bytes, every_bytes=400, every_seconds=10 ==
  append chunk-00 (240 B): buffered=240 committed=   0 flushed_now=0
  append chunk-01 (240 B): buffered=  0 committed= 480 flushed_now=1
  append chunk-02 (240 B): buffered=240 committed= 480 flushed_now=0
  append chunk-03 (240 B): buffered=  0 committed= 960 flushed_now=1
  append chunk-04 (240 B): buffered=240 committed= 960 flushed_now=0
finalize: bytes_committed=1200 checkpoints=3 final_sha256=18f7ce2728c9a11c...
sink length matches: True
final_sha256 matches direct hash of sink: True

== part 2: simulate crash by truncating last log line, then recover ==
intact_records=2 torn_trailing_record=True
resume bytes_committed=960 running_sha256=466d963ed114c2f8...
verify on disk: sha256(sink[:960]) == last_running_sha256? True

== part 3: clean recover from full intact log ==
intact_records=3 torn_trailing_record=False bytes_committed=1200

== part 4: corrupt non-trailing record is rejected loudly ==
CheckpointError raised as expected: torn record at line 1 (not trailing)

== part 5: append-after-finalize is rejected ==
CheckpointError raised as expected: append after finalize
```

Things to notice:

- Five 240-byte chunks (1200 B total) under `every_bytes=400` produce
  exactly **2 policy-flushes** (after chunks 01 and 03, when the
  buffer crosses 480 B) plus **1 finalize-flush** for the trailing
  240 B — total 3 records, matching `checkpoints=3`.
- The `final_sha256` from `finalize()` equals the direct SHA-256 of
  the sink contents, so the running hash is correct end-to-end.
- After truncating the trailing log line, `recover` reports
  `intact_records=2` (the first two flushes) and
  `torn_trailing_record=True`, and `bytes_committed=960` lines up
  with the actual prefix on disk — verified by recomputing
  `sha256(sink[:960])` and matching `last_running_sha256`.
- The clean-log recover (part 3) returns the same end state as
  `finalize` (`bytes_committed=1200`, 3 records).
- Part 4 proves the engine refuses to silently skip a corrupt
  non-trailing record. Part 5 proves the API guards against
  append-after-finalize.

## Composition

- **`agent-checkpoint-resume`** — step-boundary sibling. Use this
  template for byte streams *inside* a step; use the step
  checkpointer for step-level resume. They share the same
  "append-only JSONL with hash" disposition.
- **`streaming-chunk-reassembler`** — solves a different problem
  (out-of-order/duplicate inbound chunks). The reassembler's output
  can feed this checkpointer's `append`.
- **`structured-error-taxonomy`** — a torn-trailing-record event
  classifies as `host_io` / `retryable_after_recover`; a
  non-trailing torn record classifies as `do_not_retry, attribution=host`.
- **`agent-decision-log-format`** — emit one decision-log line per
  recover (`stream_id`, `bytes_committed`, `intact_records`,
  `torn_trailing_record`) so post-mortems can reconstruct what was
  saved and what was lost.

## Non-goals

- Writing the sink durably (`sink_write` is the caller's contract;
  use `os.fsync` or O_DSYNC there).
- Rotating, compacting, or trimming the log (operator concern).
- Encrypting checkpoint contents (compose with the redaction
  template if the stream contains sensitive data).
- Multi-stream interleaving in one log file (one log per
  `stream_id`; mixed logs raise on recover).
