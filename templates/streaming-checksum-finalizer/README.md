# streaming-checksum-finalizer

## Problem

You receive an artifact (model response, tool output, file download) as a stream of byte chunks and want a checksum over the whole thing — but only when the stream is *complete*. The naive pattern `h = sha256(); for c in chunks: h.update(c)` and then reading `h.hexdigest()` at any time happily returns a partial-but-plausible-looking hex string. A consumer that mistakes that mid-stream hex for the final digest will record a wrong checksum, and the bug is invisible until much later when an integrity check fails.

## When to use

- You hash streamed content (LLM output, file uploads, SSE payloads) and need an integrity digest at the end.
- The stream can be cancelled or error mid-flight, and you must NOT publish a digest in that case.
- Consumers of your digest are integrity checks, dedup keys, content-addressed storage — places where a wrong-but-well-formed hex string is worse than `None`.

## When NOT to use

- You only ever have the full payload in memory (`hashlib.sha256(blob)` is fine).
- You actually want a rolling/progressive hash a consumer reads as the stream grows. This template explicitly forbids that — it's the wrong tool for that job.
- You need a Merkle tree / chunked content-addressing. Use a proper Merkle implementation.

## API sketch

```python
from template import ChecksumFinalizer, StreamClosedError, StreamAbortedError

cf = ChecksumFinalizer("sha256")
for chunk in stream:
    cf.feed(chunk)

assert cf.hexdigest is None        # mid-stream: never leaks a partial
final = cf.finalize()              # commits and returns hex
assert cf.hexdigest == final       # idempotent

cf.feed(b"late")                   # -> raises StreamClosedError
```

Invariants:

- `digest` and `hexdigest` are `None` until `finalize()` is called.
- `finalize()` is idempotent and returns the same hex string every time.
- `feed()` after `finalize()` raises `StreamClosedError`.
- `abort()` is terminal: digest stays `None`, and any later `feed`/`finalize` raises `StreamAbortedError`.
- `bytes_seen` is always trustworthy (cross-check against `Content-Length`).

## Worked example invocation

```
python3 templates/streaming-checksum-finalizer/worked_example.py
```

## Failure modes covered by the design

- **Partial-digest leak**: `digest`/`hexdigest` are `None` pre-finalize; the only way to get a string is `finalize()`.
- **Late chunk after close**: `StreamClosedError` — caller's bug surfaces loudly instead of corrupting a recorded hash.
- **Cancelled / errored stream**: `abort()` poisons the object; no digest will ever be produced even if a confused caller tries.
- **Double-finalize race**: idempotent, returns the same hex without re-hashing.
- **Wrong-type input**: `feed()` rejects non-bytes-like input early with `TypeError` so the hash never gets fed something that quietly stringifies.

## Composition notes

- Pair with `streaming-chunk-reassembler` (reassemble first, hash the deliverable in-order chunks) when chunks may arrive out of order.
- Pair with `tool-call-result-validator` (cross-check `bytes_seen` against a declared length before trusting the digest).
- The hex returned by `finalize()` is a fine cache key for `tool-result-cache` content-addressed storage.
