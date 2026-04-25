# partial-json-tail-recovery

Heuristically recover a parseable object/array from a JSON blob a streaming
LLM truncated mid-emission, and tell the caller exactly **which top-level
keys are confirmed-complete vs heuristically-closed**.

## Problem

Streaming LLM responses that hit `max_tokens` produce JSON that is
*structurally* incomplete: the model was halfway through a string value,
halfway through typing the next key, or one `}` short of closing the outer
envelope. The bytes the model already emitted are usually **fine** up to some
prefix — what the caller wants is:

1. The largest valid prefix, recovered as a real Python object.
2. A clear signal about which keys were finished by the model versus which
   ones we patched our way out of.
3. A guarantee that we never *invent* values. If the tail is
   `"status": "in_pro` we drop the entire `status` key — we do not guess
   `"in_progress"` (or worse, `"in_promotion"`).

The naive responses are bad:
- `json.loads(...)` raises and you lose every committed key.
- "Just close any open braces" silently retains a half-typed key like
  `"reaso` and produces parseable-but-wrong data.
- Asking the model to retry costs another full call and may truncate again
  on a longer prompt; the orchestrator usually wants to **partially commit
  what we already have** and continue.

## Approach

A hand-rolled state machine walks the input character-by-character and
tracks:

- A **stack of openers** (`{` and `[`), which gives us LIFO closers to
  append at the cut point.
- A **phase per stack frame** (`expect_key`, `in_key`, `expect_colon`,
  `expect_value`, `in_value`, `after_value`) so we know whether the cut
  happened mid-key, mid-value, or at a clean comma boundary.
- A **pending key** per object frame; that key is only promoted to the
  committed-keys list when its **value finishes** (close brace, close
  bracket, end of literal, end of string). A key whose value is still
  open at the cut point is **not** confirmed.
- The largest **safe cut index** — the byte offset after the last
  committed value or before the trailing comma. Everything after that
  index is dropped.

Then the engine emits closers (`}` for `{`, `]` for `[`) in reverse stack
order, parses the patched string, and reports:

| field             | meaning                                                                |
|-------------------|------------------------------------------------------------------------|
| `parsed`          | The recovered Python object (`dict` / `list`), or `None` if unrecoverable |
| `confirmed_keys`  | Top-level keys whose value the **model** closed before the cut         |
| `heuristic_keys`  | Top-level keys present in `parsed` but whose value **we** closed       |
| `dropped_tail`    | The raw bytes after the safe cut index (for logging / triage)          |
| `actions`         | Ordered list of patches applied (auditable)                            |
| `status`          | `clean` / `recovered` / `unrecoverable`                                |

String scanning honors `\\`, `\"`, `\u00xx` escapes — we don't false-trip
on a backslash quote inside a string value.

## When to use

- **Streaming LLM JSON**: `max_tokens` truncations on tool-call arguments,
  structured-output endpoints, JSON-mode responses.
- **Long-poll log shippers** that hand off chunks and may flush mid-record.
- **Best-effort parse for triage**: you want to surface the incident's
  `id` and `severity` even when the model never finished `status`.

## When NOT to use

- **Any setting where partial commit is unsafe.** If a missing field would
  cause silent data corruption (transactions, RBAC decisions, payment
  bodies), **do not** use this — fail loud and re-call the model.
- **Strict schema validation.** This recovers shape, not semantics. Pair
  with a schema validator on the recovered object before acting on it.
- **Free-form prose with embedded JSON.** This expects the input to be
  *attempting* to be a single JSON value. For mixed prose + JSON, extract
  the JSON region first.

## API contract

```python
from recovery import recover, RecoveryResult

res: RecoveryResult = recover(text)

res.parsed             # dict | list | None
res.confirmed_keys     # list[str]   (top-level keys, value closed by model)
res.heuristic_keys     # list[str]   (top-level keys we closed for them)
res.dropped_tail       # str         (raw bytes after the safe cut)
res.actions            # list[str]   (audit log of patches)
res.status             # "clean" | "recovered" | "unrecoverable"
```

Invariants the engine guarantees:

1. `confirmed_keys` is computed from the **input prefix**, not the patched
   output. If a key is in `confirmed_keys`, the model emitted both the key
   and the closer of its value before the cut.
2. `confirmed_keys` and `heuristic_keys` are disjoint.
3. `parsed`'s keys are exactly `confirmed_keys ∪ heuristic_keys` for an
   object root; `heuristic_keys` is `[]` for an array root.
4. We never **fabricate** a value. If a string value is mid-emission, the
   key is dropped, not patched with the partial string.
5. A trailing comma at the cut is dropped, not preserved.
6. A half-typed key (`"reaso` with no closing quote) is dropped along with
   any pending colon / value bytes.

## Edge cases handled

- **Mid-string-value cut** (`"status": "in_pro`) → key `status` dropped,
  prior keys preserved.
- **Mid-key cut** (`"rea` after a comma) → trailing comma + half key dropped,
  prior keys preserved.
- **Nested arrays of objects**, cut inside an inner element. The outer
  array is closed heuristically; intact inner elements survive; the
  partially-typed inner element is recovered with only its committed
  fields.
- **Bare-literal cut** (`"page": tr`) → literal not committed, key dropped.
- **Already-valid input** → fast path, `status="clean"`, no patches.
- **Empty / whitespace-only input** → `status="unrecoverable"`,
  `parsed=None`.
- **Strings containing `}` or `]`** → not mistaken for closers (proper
  in-string state).
- **Escaped quotes inside strings** (`"msg": "he said \"hi\""`) → handled
  by the escape-state.

## Tradeoffs

- **Heuristic, not optimal.** We pick the *largest safe prefix*; we do not
  try to micro-recover individual half-fields (e.g. parse `"status": "in_pro`
  as `"status": "in_pro"` by guessing where the close-quote should go).
  Guessing values is *worse* than dropping them.
- **No streaming API.** This is a one-shot recovery on a complete buffer.
  For true streaming, run a JSON-streaming parser (e.g.
  `partial-json-streaming-parser` template) and only fall back to this
  engine when the stream ends mid-emission.
- **No schema awareness.** A recovered object may pass parse but still be
  invalid for your downstream tool. Validate after recovery.
- **Object-root bias.** `confirmed_keys` / `heuristic_keys` only carry
  meaning for a top-level object. For an array root the lists are empty
  even though `parsed` is correct.

## Composes with

- `partial-json-streaming-parser` — that template handles in-flight chunks;
  this template handles the final torn buffer.
- `agent-output-validation` — feed `res.parsed` into a schema validator
  before acting on it.
- `structured-error-taxonomy` — `status="unrecoverable"` classifies as
  `do_not_retry` (the bytes are corrupt) when triggered by host I/O, but as
  `retryable_after_recover` when triggered by `max_tokens`.

## Example output

Scenario 1 (mid-string-value cut, model committed 3 keys cleanly):

```
status            : recovered
confirmed_keys    : ['id', 'severity', 'summary']
heuristic_keys    : []
dropped_tail      : ', "status": "in_pro'
actions           :
  - dropped tail: ', "status": "in_pro'
  - appended closers: }
parsed            :
{
  "id": "INC-4421",
  "severity": 3,
  "summary": "queue fell behind during nightly batch"
}
```

Scenario 3 (nested array of events, cut inside the second element):

```
status            : recovered
confirmed_keys    : ['incident_id']
heuristic_keys    : ['events']
dropped_tail      : ', "kind": "ack'
actions           :
  - dropped tail: ', "kind": "ack'
  - appended closers: }]}
parsed            :
{
  "events": [
    {"kind": "alert", "page": true, "t": 1730000000},
    {"t": 1730000060}
  ],
  "incident_id": "INC-77"
}
```

Note: `events` is in `heuristic_keys` (we closed the array), not
`confirmed_keys` (the model never emitted the closing `]`). The first
event survives intact; the second event survives with only its committed
field `t`. The half-typed `"kind": "ack` is dropped — we do **not** guess
`"ack"` or `"acknowledge"`.

Run it:

```bash
python3 templates/partial-json-tail-recovery/worked_example.py
```

Stdlib-only. No third-party deps.
