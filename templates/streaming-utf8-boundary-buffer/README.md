# streaming-utf8-boundary-buffer

A stdlib-only buffer that holds back a partial trailing UTF-8 sequence at chunk boundaries so a streamed byte source (SSE, HTTP chunked, subprocess pipe) never emits half a codepoint to a downstream text consumer.

## The problem

Streaming APIs deliver bytes, not text. The bytes that carry one Unicode codepoint can land in two different chunks. The naive code is:

```python
for chunk in stream:                     # chunk: bytes
    yield chunk.decode("utf-8")          # ← this raises UnicodeDecodeError
```

…which raises at the first chunk that ends inside a multibyte codepoint. The "fix" most people reach for next is `errors="replace"`, which silently turns `中` into two `\ufffd` replacement characters and quietly corrupts every CJK / emoji / accented stream the moment chunk boundaries don't line up with codepoint boundaries.

The right fix is structural, not statistical. UTF-8 is self-synchronizing: the leading byte of every codepoint encodes the total length (1, 2, 3, or 4 bytes), and continuation bytes have a distinct top-bit pattern (`10xxxxxx`). Given any byte buffer you can compute *exactly* how many trailing bytes might still be the start of an incomplete codepoint (always 0..3) and hold only those back for the next chunk.

## The shape of the solution

```python
buf = Utf8BoundaryBuffer()
for chunk in stream:                     # chunk: bytes
    text = buf.feed(chunk)               # str — only complete codepoints
    if text:
        consumer(text)
tail = buf.flush()                       # raises if stream ended mid-codepoint
if tail:
    consumer(tail)
```

Three guarantees:

1. **Every byte returned to the consumer decodes cleanly.** No `\ufffd` replacement characters introduced by the buffer; no truncated multibyte sequences.
2. **Held-back bytes are bounded at 3.** UTF-8 codepoints are at most 4 bytes; we hold back at most the last 3 if they look like the start of an incomplete sequence.
3. **A torn stream fails loudly at `flush()`.** If the stream actually ends inside a codepoint, `flush()` raises `Utf8BoundaryError` with the held-back bytes in the message — the caller chooses whether to log, repair, or treat as upstream truncation. We never silently emit a partial codepoint.

## Conventions implemented

- `feed(chunk: bytes) -> str` — decode and return the largest complete UTF-8 prefix; retain a 0..3 byte tail.
- `flush() -> str` — call once at EOF. If held-back bytes are not a valid (now-completed) UTF-8 sequence, raises `Utf8BoundaryError` and clears the buffer.
- **Strict decode of complete prefixes.** If a *complete* prefix contains an invalid byte (a `\xff`, an overlong encoding), `feed()` raises `UnicodeDecodeError` immediately rather than deferring to `flush()` when the offending bytes are far behind us.
- `pending_bytes`, `total_emitted_chars`, `total_fed_bytes` — observability for tests and metrics.
- No clocks, no I/O, no threads. The buffer is a value object; the caller decides how to drive it (sync loop, asyncio iterator, thread).

## When to use it

- Anywhere a streaming byte source is being fed into something that expects `str`: SSE token streams from LLM providers, HTTP chunked downloads piped into a parser, `subprocess.Popen.stdout.read(n)` loops.
- Sitting *before* `partial-json-streaming-parser` so the parser only ever sees valid UTF-8 (the parser handles structural truncation; this handles encoding truncation — different problems, both real).
- In any pipeline where you currently call `chunk.decode("utf-8", errors="replace")` to make `UnicodeDecodeError` go away. That call is hiding a correctness bug; this template fixes it.

## When NOT to use it

- If you can hand the whole byte stream to `io.TextIOWrapper` and *only* read from the wrapper, do that — `TextIOWrapper` already handles boundary buffering. Use this template when you must touch raw bytes for transport reasons (SSE event framing, length-prefixed chunks) and only need text *after* you've split events.
- For non-UTF-8 encodings. UTF-16 has its own surrogate-pair boundary rules; CJK legacy encodings (Shift-JIS, GB18030) have different leading-byte heuristics. This template is UTF-8 specific on purpose.
- For *line-oriented* streaming where you'd rather buffer until `\n` and decode whole lines. Just buffer at the line layer if that's what your consumer wants.

## Failure modes the implementation defends against

1. **Codepoint split across chunk boundary.** `b"hi \xe4\xb8"` + `b"\xad ok"` correctly emits `"hi "` then `"中 ok"`.
2. **4-byte emoji split at any of three offsets.** Worked example exhaustively splits `"cat 🐱 sees 🐱!"` at every byte position inside both emoji and round-trips byte-identical.
3. **Continuation-only second chunk.** `b"hola \xc3"` + `b"\xb1"` correctly emits `"hola "` then `"ñ"` even though the second chunk is a single continuation byte.
4. **Stream torn at EOF.** A stream that ends with a 2-of-3 byte sequence reports `pending_bytes=2` after the last `feed()` and `flush()` raises `Utf8BoundaryError: stream ended with 2 byte(s) of incomplete utf-8: b'\xe4\xb8' (unexpected end of data)`.
5. **Invalid byte mid-prefix.** `b"good \xff bad"` raises `UnicodeDecodeError` *immediately* on `feed()`, not deferred to `flush()`.
6. **Held-back bytes after an unrecognizable leading byte.** Bytes whose top bits don't match any valid UTF-8 leader pattern are NOT held back — they're left in the buffer so the next decode raises, instead of being silently swallowed.

## Files in this template

- `utf8_boundary_buffer.py` — stdlib-only reference (~120 lines), one dataclass + one helper.
- `worked_example.py` — six scenarios: clean ASCII, split 3-byte codepoint, split 4-byte emoji at six offsets, continuation-only second chunk, torn at EOF, invalid byte in complete prefix.

## Sample run

```text
== clean_ascii ==
  emitted: 'hello world'
  pending_bytes after flush: 0
== split_3byte_codepoint ==
  feed(b'hi \xe4\xb8') -> 'hi '  pending=2
  feed(b'\xad ok')        -> '中 ok'  pending=0
  full: 'hi 中 ok'
== split_4byte_emoji ==
  raw bytes: 63 61 74 20 f0 9f 90 b1 20 73 65 65 73 20 f0 9f 90 b1 21
  split@ 5  pending_after_first_feed=?  full_ok=True
  split@ 6  pending_after_first_feed=?  full_ok=True
  split@ 7  pending_after_first_feed=?  full_ok=True
  split@13  pending_after_first_feed=?  full_ok=True
  split@14  pending_after_first_feed=?  full_ok=True
  split@15  pending_after_first_feed=?  full_ok=True
== continuation_only_chunk ==
  a='hola '  b='ñ'  c=''  total='hola ñ'
== torn_at_eof ==
  a='oops '  pending_bytes=2
  flush() raised: stream ended with 2 byte(s) of incomplete utf-8: b'\xe4\xb8' (unexpected end of data)
== invalid_byte_in_complete_prefix ==
  feed() raised: invalid start byte

All assertions passed.
```

The `split_4byte_emoji` scenario is the one that justifies the template: each of the six split offsets lands inside a multibyte sequence, every naive `chunk.decode("utf-8")` would raise on at least one of them, and `errors="replace"` would silently corrupt the emoji to two replacement characters. Here all six round-trip byte-identical.

The `torn_at_eof` scenario is the second justification: when a stream really does end mid-codepoint (upstream crash, deadline expiry, `max_tokens` cut on a CJK token), `flush()` surfaces the held-back bytes loudly. A consumer can then escalate to a continuation prompt or mark the output as truncated rather than ship a half-character to the user.

## Composes with

- **`partial-json-streaming-parser`** — feed this buffer's `str` output into the parser so the parser never sees half a codepoint.
- **`streaming-chunk-reassembler`** — that template handles out-of-order *seq*-numbered chunks; this one handles within-chunk encoding boundaries. Reassemble first, then UTF-8-buffer.
- **`model-output-truncation-detector`** — a `flush()` that raises `Utf8BoundaryError` is a strong "stream was cut" signal to feed into the truncation verdict alongside `finish_reason`.
- **`sse-reconnect-cursor`** — on reconnect, discard any held-back bytes from the previous connection (they're meaningless in the new TCP stream); start a fresh `Utf8BoundaryBuffer`.
