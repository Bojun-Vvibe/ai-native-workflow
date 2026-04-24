# Template: Partial JSON streaming parser

Incrementally parse a JSON object that arrives in chunks (as from a
streaming model output), exposing the **current best-effort view** of
the object after every chunk.

Pure stdlib. No `ijson`, no event callbacks, no SAX. Just
`feed(chunk)` and `snapshot()`.

## Why this exists

When a model streams `{"plan": [...], "answer": "..."}` token by
token, you usually want to:

- Render the `plan` array to the UI as soon as each step lands.
- Start executing tool calls embedded in the plan before the trailing
  `"answer"` string has even begun streaming.
- Detect schema-violations (missing keys, wrong types) early enough
  to cancel the stream and re-prompt — instead of paying for the
  full output and then discovering it was malformed.

A "wait for the closing brace then `json.loads`" approach makes
streaming pointless. A SAX-style event parser works but forces you
to maintain a parallel state machine just to reconstruct the same
dict you'd have gotten anyway. This template uses a third approach:
**prefix-completion**. After every chunk it appends the minimal
suffix (`"`, `]`, `}`) that would close the open structures, parses
the synthesized string, and surfaces that as the snapshot. The
snapshot only ever moves forward; partial junk is silently held back
until the next viable chunk.

## When to use

- You consume model output as a stream and need to render or act on
  it before completion.
- Your output schema is "object-shaped" (one root JSON object) — not
  NDJSON, not multiple top-level values.
- You can tolerate the snapshot moving in discrete jumps as fields
  finish; you don't need character-by-character UI updates.

## When NOT to use

- The stream is **NDJSON** (one JSON value per line). Use a line
  splitter and `json.loads` per line; this template is overkill and
  the wrong abstraction.
- The output is enormous (megabytes). Re-parsing the full buffer on
  every chunk is O(n²) in chunk count. Switch to a real incremental
  parser like `ijson`.
- You need the events ("entered object", "saw key X") rather than
  the materialized object. Use a SAX-style parser instead.

## Anti-patterns

- **"Just regex out the array."** Works for one schema, breaks the
  next time the model nests something. Don't.
- **Updating UI from `_last_good` blindly.** The snapshot can mutate
  shape between chunks (a string field appears, a number gets
  precision). Diff against the previous snapshot, don't blindly
  re-render.
- **Trusting the snapshot's terminal values.** A string field that
  reads `"hello"` mid-stream may end up `"hello world"` at
  completion. Only act on a field once `parser.complete` is `True`,
  or once the next field has appeared (which proves the prior field
  is closed).
- **Letting the buffer grow unbounded on a stuck stream.** Wrap with
  a max-bytes guard so a misbehaving server can't OOM you.
- **Returning the snapshot through an exception path.** `feed()`
  here always returns the best-effort view; it never raises on
  malformed prefixes. If yours does, agents downstream will start
  swallowing it and you'll lose visibility.

## Files

- `src/streaming_parser.py` — `StreamingJSONParser` dataclass with
  `feed(chunk) -> object`, `snapshot()`, `complete: bool`, and a
  `history` list of every materialized snapshot for debugging.
- `examples/run_example.py` — simulates a 10-chunk stream with
  deliberately ugly chunk boundaries (mid-string, mid-number,
  mid-key) and prints the snapshot evolution.

## Verified output

Running `python3 examples/run_example.py`:

```
# streaming-json-parser demo  (10 chunks)

chunk  1  bytes_in= 10  complete=False  plan_steps=0  has_answer=False
          snapshot: {"plan": []}
chunk  2  bytes_in= 32  complete=False  plan_steps=1  has_answer=False
chunk  3  bytes_in=  8  complete=False  plan_steps=1  has_answer=False
          snapshot: {"plan": [{"action": "read README.md", "step": 1}]}
chunk  4  bytes_in= 15  complete=False  plan_steps=1  has_answer=False
chunk  5  bytes_in= 29  complete=False  plan_steps=2  has_answer=False
chunk  6  bytes_in= 40  complete=False  plan_steps=3  has_answer=False
          snapshot: {"plan": [{"action": "read README.md", "step": 1},
                              {"action": "list templates dir", "step": 2},
                              {"action": "pick two angles", "step": 3}]}
chunk  7  bytes_in= 19  complete=False  plan_steps=3  has_answer=False
chunk  8  bytes_in=  2  complete=False  plan_steps=3  has_answer=False
          snapshot: {"confidence": 0.87, "plan": [...]}
chunk  9  bytes_in= 30  complete=False  plan_steps=3  has_answer=True
chunk 10  bytes_in= 14  complete=True   plan_steps=3  has_answer=True

final snapshot equals fully-buffered parse?  True
```

Note chunks 7 → 8: the buffer ended with `0.` (a partial number,
which `json.loads` rejects), so the snapshot at chunk 7 still showed
no `confidence` field. At chunk 8 the trailing `87` arrived, the
number became `0.87`, and the snapshot advanced. This is the kind of
discrete jump your UI needs to be ready for — never trust mid-stream
numeric precision.

## Composing with other templates

- Pair with [`streaming-chunk-reassembler`](../streaming-chunk-reassembler/)
  if your transport layer fragments chunks at byte boundaries below
  the JSON token level.
- Pair with [`structured-output-repair-loop`](../structured-output-repair-loop/)
  for the case where the *completed* parse is structurally invalid
  (missing keys, wrong types) and you want a re-prompt.
- Pair with [`model-output-truncation-detector`](../model-output-truncation-detector/)
  to distinguish "stream closed cleanly with `complete=False`" (model
  was cut off) from "stream completed normally."
