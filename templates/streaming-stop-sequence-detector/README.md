# streaming-stop-sequence-detector

## Problem

When an LLM streams tokens to you, you often want to stop generation (or stop forwarding to the user) the moment a particular stop string appears — e.g. `</stop>`, `\n\nUser:`, or a custom turn boundary marker. The naive approach `chunk.find(stop)` fails when the stop string straddles a chunk boundary (`"...hello </st"` then `"op> ..."`). Naively concatenating the entire stream defeats the point of streaming.

## When to use

- Your model returns text in many small chunks (SSE / token stream).
- You need to detect one or more stop sequences and stop emitting as soon as one appears.
- You want to forward the safe prefix to the user with minimum latency.
- You don't want to ship a regex engine or rebuild the entire output string per chunk.

## When NOT to use

- The model server already enforces stop sequences server-side and never emits past them. Then this is dead weight.
- You need fuzzy / token-id-aware stops (BPE boundaries inside a token). This template operates on text, not token IDs.

## API sketch

```python
from template import StopSequenceDetector

det = StopSequenceDetector(["</stop>", "\n\nUser:"])
for chunk in stream:
    safe, hit = det.feed(chunk)
    sink.write(safe)
    if hit is not None:
        stop_string, idx_in_combined = hit
        break
else:
    sink.write(det.flush())   # stream ended naturally
```

Invariants:

- `safe` never contains any prefix of any stop sequence at its trailing edge.
- The detector buffers at most `max(len(s) for s in stops) - 1` characters.
- After `hit` is returned, `feed` and `flush` are no-ops (`done == True`).
- `idx_in_combined` is the position in `(leftover_buffer + new_chunk)` at the call that detected the hit — useful if you want to inspect the suffix.

## Worked example invocation

```
python3 templates/streaming-stop-sequence-detector/worked_example.py
```

## Worked example output

```
=== boundary-spanning hit ===
  chunk[0]='hello world </st'                       -> emit='hello worl'                   hit=None
  chunk[1]='op> trailing garbage'                   -> emit='d '                           hit=('</stop>', 2)
  total emitted: 'hello world '
  hit: ('</stop>', 2)

=== three-chunk straddle ===
  chunk[0]='answer is 42.'                          -> emit='answer '                      hit=None
  chunk[1]='\n\nUs'                                 -> emit='is 4'                         hit=None
  chunk[2]='er: next question'                      -> emit='2.'                           hit=('\n\nUser:', 2)
  total emitted: 'answer is 42.'
  hit: ('\n\nUser:', 2)

=== earliest of multiple stops ===
  chunk[0]='abc STOP def </stop> ghi'               -> emit='abc '                         hit=('STOP', 4)
  total emitted: 'abc '
  hit: ('STOP', 4)

=== no hit, flush tail ===
  chunk[0]='alpha '                                 -> emit=''                             hit=None
  chunk[1]='beta '                                  -> emit=''                             hit=None
  chunk[2]='gamma'                                  -> emit='alph'                         hit=None
  flush -> 'a beta gamma'
  total emitted: 'alpha beta gamma'
  hit: None

=== stop at start ===
  chunk[0]='Xafter'                                 -> emit=''                             hit=('X', 0)
  total emitted: ''
  hit: ('X', 0)

all assertions passed
```

Note in the "three-chunk straddle" case how the stop `\n\nUser:` (length 7) is split across `\n\nUs` and `er: next question` and is still detected — the detector retained the 6-char tail between feeds.

## Failure modes covered by the design

- **Boundary-spanning stop**: handled by retaining `max_len - 1` chars between feeds.
- **Multiple competing stops**: earliest position wins (deterministic, not insertion-order).
- **Stream ends without hit**: caller must invoke `flush()` to drain the retained tail.
- **Empty / zero-length stop**: rejected at construction.
- **Double-fire after hit**: `done` flag latches; subsequent `feed`/`flush` return empty.
