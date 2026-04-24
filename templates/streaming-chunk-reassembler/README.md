# `streaming-chunk-reassembler`

Reassemble an LLM (or any producer's) streamed chunks into the original
ordered stream when the transport may deliver chunks **out of order**,
**duplicated**, or with **persistent gaps**.

The motivating cases are real:

- A streaming-token API behind a load balancer where two replicas
  occasionally double-emit the same `seq` because of a flapping
  upstream connection.
- A retry layer that re-issues an in-flight request and the original
  partial response races the new full response.
- A multi-region edge proxy that reorders chunks under network jitter.
- A persistent gap caused by a dropped intermediate chunk that the
  caller eventually has to give up on.

The reassembler is pure: no I/O, no clocks, no retransmit logic. It
takes a chunk in, returns the (possibly empty) list of chunks that
became deliverable in order. Callers compose it with their own
transport, timeout, and retry policy.

## SPEC

### Chunk shape

```python
{"seq": int, "data": str, "is_final": bool}
```

- `seq` ≥ 0, monotonically increasing by 1 from the producer.
- `data` may be the empty string (common pattern for a final
  "end of stream" marker).
- Exactly one chunk in the stream may have `is_final=True`.

### API

`StreamReassembler()` — single-stream, single-thread. Create one per
stream.

| Method | Returns | Notes |
|---|---|---|
| `accept(chunk)` | `list[dict]` | Chunks that became deliverable, in `seq` order. |
| `state()` | `dict` (sorted keys) | Snapshot suitable for a heartbeat/log line. |
| `gap_seqs()` | `list[int]` | Missing seqs between `next_expected_seq` and the highest seen seq. |
| `is_complete()` | `bool` | True iff a `is_final=True` chunk has been delivered AND no gaps remain. |

### Invariants

1. **Each `seq` is delivered AT MOST ONCE.** A duplicate with the same
   payload is silently absorbed (idempotent).
2. **Chunks are delivered in strict `seq` order.** Caller can
   concatenate `data` directly.
3. **A duplicate `seq` with a *different* payload raises
   `InconsistentChunk`.** Two flapping upstream replicas cannot
   silently corrupt the stream.
4. **`is_final` cannot move.** Setting `is_final=True` at a different
   `seq` than a previous one raises `InconsistentChunk`.

### Out of scope

- Retransmit requests (the caller decides — see `gap_seqs()`).
- Timeouts and clocks (the caller injects).
- Multi-stream multiplexing (use one reassembler per stream).

## Files

- `reassembler.py` — pure stdlib reference implementation.
- `examples/example_1_out_of_order.py` — out-of-order arrival with one duplicate.
- `examples/example_2_gap_and_inconsistent_dup.py` — persistent gap and inconsistent-payload duplicate refusal.

## Worked example output — `example_1_out_of_order.py`

The producer emits 5 chunks (`seq=0..4`); the transport delivers them
in arrival order `[0, 2, 4, 1, 2, 3]` (note seq=2 arrives twice). The
reassembler yields the original ordered text exactly once:

```
arrival seq=0 -> delivered_now=[0] state={"buffered_seqs": [], "delivered_count": 1, "final_seq": null, "gap_seqs": [], "is_complete": false, "next_expected_seq": 1}
arrival seq=2 -> delivered_now=[] state={"buffered_seqs": [2], "delivered_count": 1, "final_seq": null, "gap_seqs": [1], "is_complete": false, "next_expected_seq": 1}
arrival seq=4 -> delivered_now=[] state={"buffered_seqs": [2, 4], "delivered_count": 1, "final_seq": 4, "gap_seqs": [1, 3], "is_complete": false, "next_expected_seq": 1}
arrival seq=1 -> delivered_now=[1, 2] state={"buffered_seqs": [4], "delivered_count": 3, "final_seq": 4, "gap_seqs": [3], "is_complete": false, "next_expected_seq": 3}
arrival seq=2 -> delivered_now=[] state={"buffered_seqs": [4], "delivered_count": 3, "final_seq": 4, "gap_seqs": [3], "is_complete": false, "next_expected_seq": 3}
arrival seq=3 -> delivered_now=[3, 4] state={"buffered_seqs": [], "delivered_count": 5, "final_seq": 4, "gap_seqs": [], "is_complete": true, "next_expected_seq": 5}

final delivered seq order: [0, 1, 2, 3, 4]
reassembled text: 'The quick brown fox.'
is_complete: True
total chunks delivered: 5
```

Things to notice:

- The duplicate `seq=2` (5th arrival) returned `delivered_now=[]` —
  silently absorbed, not re-delivered, no exception.
- `gap_seqs` shrinks from `[1, 3]` to `[3]` to `[]` as the prefix
  fills, so a heartbeat consumer can tell a *recovering* gap from a
  *stuck* one.
- `is_complete` stays `false` until the prefix before `final_seq=4`
  is fully drained.

## Worked example output — `example_2_gap_and_inconsistent_dup.py`

A persistent missing chunk (`seq=1` never arrives), then a flapping
replica sends `seq=2` again with a *different* payload:

```
after seq=0: delivered=[0] state={"buffered_seqs": [], "delivered_count": 1, "final_seq": null, "gap_seqs": [], "is_complete": false, "next_expected_seq": 1}
after seq=2: delivered=[] state={"buffered_seqs": [2], "delivered_count": 1, "final_seq": null, "gap_seqs": [1], "is_complete": false, "next_expected_seq": 1}
after seq=3: delivered=[] state={"buffered_seqs": [2, 3], "delivered_count": 1, "final_seq": 3, "gap_seqs": [1], "is_complete": false, "next_expected_seq": 1}

caller observes persistent gap: [1]
is_complete (should be False, gap=[1]): False

attempting to accept duplicate seq=2 with different payload...
InconsistentChunk raised as expected: seq=2 arrived twice with different payload

re-sending seq=2 with the ORIGINAL payload (idempotent)...
delivered=[] (must be empty: already buffered)
```

Things to notice:

- After the final chunk arrives at `seq=3`, the stream is **still not
  complete** — the gap at `seq=1` blocks delivery. The caller is the
  one to decide when to give up (e.g. timeout, send a NACK, fail the
  request); the reassembler stays honest and reports `gap_seqs=[1]`.
- A flapping replica's contradictory payload is rejected loudly.
  Silent overwriting would corrupt the reassembled stream — that
  would be the worst possible failure mode for this primitive.
- A genuine duplicate with the same payload is absorbed silently
  (idempotent). The caller can safely retry transport delivery.

## Composition

- **`tool-call-retry-envelope`** — a transport-layer retry of a
  streaming request can produce duplicate chunks; this reassembler
  makes those duplicates safe.
- **`partial-failure-aggregator`** — when N parallel streams are in
  flight, each gets its own reassembler; the aggregator decides what
  to do when M of N report `is_complete()=False` past a deadline.
- **`structured-error-taxonomy`** — `InconsistentChunk` is the
  canonical "stream integrity violated" signal; classify it as
  `do_not_retry` (the upstream is contradicting itself).

## Non-goals / why this is small

This template intentionally does NOT:

- Negotiate retransmits with the producer (out of scope; protocol-specific).
- Buffer indefinitely (the caller MUST decide when to give up; we
  expose `gap_seqs()` so they can).
- Handle multi-stream demuxing (one reassembler per stream is simpler
  and always correct).
