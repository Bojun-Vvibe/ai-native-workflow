# streaming-line-delimiter-buffer

Pure, allocation-conscious line buffer for line-delimited byte streams
(NDJSON, SSE `data:` lines, log tails, framed protocols). Never returns
a partial line, joins multi-byte delimiters split across chunk
boundaries (e.g. CRLF), defends against unbounded
delimiter-starved input via `max_line_bytes`, and gives the caller an
explicit lenient-vs-strict policy for the trailing record at stream
close.

## When to reach for this

- You're consuming an NDJSON / JSONL stream from an LLM gateway,
  agent log tail, or `kubectl logs -f` and the upstream gives you
  bytes, not records.
- You're parsing SSE and need to split on `\n\n` (event boundary) or
  `\n` (within an event) without accidentally splitting `data:` value
  bytes that happen to contain a `\r`.
- You inherited code that does `chunk.decode().split("\n")` and you
  have started seeing UTF-8 errors and "JSON is not a valid object"
  bug reports — both symptoms of partial-line delivery.

## When NOT to reach for this

- You need framing on **byte counts**, not delimiters (use a length-
  prefix codec).
- You need UTF-8-codepoint-safe streaming text (compose with
  `streaming-utf8-boundary-buffer` *after* this — line-split first
  in bytes, then decode each complete line).
- You need pull-based async iteration. This is sync and pure on
  purpose; wrap it in your own producer.

## Files

| File | Purpose |
| --- | --- |
| `line_buffer.py` | The `LineBuffer` class. Stdlib only. ~110 lines. |
| `example.py` | Five-part runnable worked example. |

## Contract

```
buf = LineBuffer(delimiter=b"\n", max_line_bytes=1<<20, strict_trailing=False)
for chunk in transport:
    for line in buf.feed(chunk):     # bytes, delimiter stripped
        handle(line)
for line in buf.close():              # flush trailing record
    handle(line)
```

Invariants worth tattooing:

1. `feed` never returns a partial line.
2. The delimiter may straddle a chunk boundary (`b"...\r"` then
   `b"\n..."` with `delimiter=b"\r\n"` joins correctly).
3. `feed(b"")` is a no-op, **not** an end-of-stream signal. `close()`
   is the only end-of-stream signal.
4. A line longer than `max_line_bytes` raises `LineTooLong` *before*
   the delimiter arrives — we will not pin unbounded memory waiting
   for a delimiter that may never come.
5. `close()` and `feed()` after close raise `BufferClosed`.
6. With `strict_trailing=True`, a non-empty unterminated trailing
   record raises `UnterminatedTrailingLine` instead of being
   yielded — useful for protocols where every record MUST be
   delimiter-terminated (NDJSON-strict, JSON-Lines).

## Composes with

- **streaming-utf8-boundary-buffer** — split lines first (this), then
  hand each complete line to a UTF-8 decoder. Don't reverse the order
  or a multibyte codepoint that straddles a chunk boundary inside a
  line will trip you.
- **streaming-chunk-reassembler** — if your transport delivers
  out-of-order chunks, reassemble first; this buffer assumes
  in-order bytes.
- **structured-error-taxonomy** — `LineTooLong` is `do_not_retry,
  attribution=upstream`; `UnterminatedTrailingLine` is
  `do_not_retry, attribution=upstream`; `BufferClosed` is
  `do_not_retry, attribution=local` (caller bug).

## Sample run

Output of `python3 example.py`, copied verbatim:

```

--- Part 1: NDJSON dripped one byte at a time ---
emitted 4 lines (expected 4)
  step= 0 event=start
  step= 1 event=tool_call
  step= 2 event=tool_result
  step= 3 event=done

--- Part 2: CRLF delimiter split across chunk boundary ---
out = [b'event: token', b'data: hello']

--- Part 3: trailing line at close (lenient vs strict) ---
lenient: [b'line-a', b'line-b-no-newline']
strict raised as expected: stream closed with 17-byte unterminated trailing line under strict_trailing=True (length=17)

--- Part 4: LineTooLong defends against delimiter-starved streams ---
raised LineTooLong(observed=200, limit=64) — buffer cleared
recovery feed after raise: [b'short']

--- Part 5: post-close calls raise BufferClosed ---
feed() after close raised: feed() after close()
close() after close raised: close() called twice

All 5 parts OK.
```

The five parts cover, in order: chunk-size-independence (one byte at
a time still produces exactly the right four NDJSON records); a
multi-byte CRLF delimiter split across the boundary still joins
into two correctly-framed lines; the lenient-vs-strict policy choice
for trailing records is explicit at `close()` time; a 200-byte
delimiter-starved feed raises `LineTooLong` *before* close (the
buffer would otherwise grow unbounded waiting for a delimiter that
never arrives) and the buffer remains usable for subsequent valid
input; and post-close `feed`/`close` calls raise `BufferClosed` so
caller bugs surface loudly instead of silently dropping data.
