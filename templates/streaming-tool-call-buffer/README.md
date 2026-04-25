# streaming-tool-call-buffer

Buffer streaming tool-call deltas from an LLM and dispatch each tool
call **exactly once**, only when its arguments are complete and valid
JSON.

## What problem it solves

Streaming chat APIs (OpenAI-compatible, Anthropic, and friends) deliver
tool calls as a sequence of small SSE deltas. A single call's JSON
`arguments` field is split across many fragments, calls can be
interleaved by `index`, and nothing in the wire format tells you up
front "this fragment is the last one" — the call is only really done
when the stream advances past it, finalizes it, or ends.

Naive hosts make one of three classic mistakes:

1. Dispatch on every delta → fire the same tool 12 times.
2. `json.loads` each fragment and silently swallow `JSONDecodeError` →
   either drop the whole call or, worse, dispatch with a half-parsed
   blob that happens to be momentarily valid.
3. Wait for the stream to fully end → blow latency for tools that
   could have started earlier.

This template gives you a tiny stateful buffer that:

- Accumulates per-`index` (`name`, `arguments`) fragments.
- Detects completion via three independent signals: an explicit
  `finalize`, the stream advancing to a higher index, or end-of-stream.
- Only emits a call once arguments parse as a JSON object.
- Routes malformed calls to a separate `on_malformed` sink instead of
  dropping them — so a bad call becomes a quarantine record, not a
  silent gap in your trace.

## When to use it

- You speak directly to a streaming chat completion API and need to
  bridge tool calls into a synchronous dispatcher.
- You want one canonical place to decide "this call is ready", instead
  of scattering `try/except json.JSONDecodeError` across handlers.
- You need an audit trail of malformed calls (e.g. for prompt
  regression analysis or model-quality dashboards).

## When NOT to use it

- Your provider's SDK already gives you fully-assembled tool calls
  (most non-streaming endpoints, plus some SDKs that buffer for you).
  Use those.
- You need cross-turn deduplication or idempotency. That's a different
  layer — see `templates/tool-call-idempotency-key/` and
  `templates/tool-call-retry-envelope/`.
- You need to stream tool **results** back to the model. This template
  is request-side only.

## Files

- `buffer.py` — `StreamingToolCallBuffer` class, plus `CompletedCall`
  and `MalformedCall` dataclasses. Stdlib only.
- `worked-example/run.py` — replays a 12-delta SSE session that
  produces 2 dispatchable calls and 1 quarantined call.

## Wire shape it expects

Each delta is a dict with any subset of:

| Key | Meaning |
|---|---|
| `index` | Which tool call this fragment belongs to (default `0`). |
| `id` | Provider-side call id; populated once. |
| `name` | Tool name; populated once. |
| `arguments` | A JSON-fragment string; concatenated across deltas. |
| `finalize` | Bool; truthy means "this call is done". |

Anthropic-style `input_json_delta` events normalize cleanly into this
shape — set `index` from `content_block.index`, accumulate
`partial_json` into `arguments`, and emit a `finalize: True` when you
see the matching `content_block_stop`.

## Demo

```
=== Completed calls ===
  [#0] search_repo({"limit": 5, "query": "retry budget"})  id=call_a1
  [#2] list_open_prs({})  id=call_c3

=== Quarantined (malformed) calls ===
  [#1] open_file -> invalid JSON: Expecting property name enclosed in double quotes at pos 37
     raw: '{"path": "src/agent.py", "line": 42, oops'

summary: 2 dispatched, 1 quarantined, 12 deltas consumed
self-check: OK
```

The example exercises all three completion paths: implicit completion
when the stream advances index 0 → 1, an explicit `finalize` on a
malformed call (which lands in the quarantine sink instead of the
dispatcher), and a finalize-only zero-arg call.
