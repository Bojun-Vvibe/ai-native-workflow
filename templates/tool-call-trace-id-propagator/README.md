# tool-call-trace-id-propagator

W3C-traceparent-style request id (`trace_id`) that flows through arbitrarily
nested agent tool calls, plus per-call `span_id` and `parent_span_id` so
downstream logs from any layer (orchestrator, sub-agent, tool implementation,
vendor SDK) become joinable on `trace_id` and reconstructable into a tree by
walking `parent_span_id`.

## What it solves

Without a propagated trace id, debugging an agent mission means manually
correlating timestamps across at least four log streams (host process,
sub-agent, tool implementation, vendor SDK). With a propagated `trace_id`
plus `(span_id, parent_span_id)` you get one keyed lookup and a clean tree.

The wire format is intentionally one fixed-shape ASCII line so it can be
carried by any tool-call envelope (HTTP header, JSON field, env var,
log line) without negotiation.

## Wire format

```
v=1;trace=<32-hex>;span=<16-hex>;parent=<16-hex|0000000000000000>;flags=<2-hex>
```

- `trace` — allocated once per top-level mission/request, never changes.
- `span` — fresh per call (16 random hex chars). Never all-zero.
- `parent` — calling span's `span`; root call carries the all-zero parent
  so every trace has exactly one root.
- `flags` — bitfield. Bit 0 = sampled. Bit 1 = synthetic (framework-injected
  span, e.g. an automatic retry, useful when filtering).

Versioning is explicit (`v=1`); a parser rejects any other version so a v2
deployment cannot silently mix with a v1 collector.

## Structural guarantees

- **Header round-trip is lossless.** `parse(ctx.header()) == ctx`.
- **Sampled bit is inherited.** A `child(parent)` cannot promote an unsampled
  trace to sampled — the framework never overrides the upstream decision.
- **Synthetic bit is monotonic per branch.** `child(..., synthetic=True)`
  sets it; ancestors are unaffected.
- **Validator catches `orphan_span`** when an intermediate hop's span never
  flushed (process crash before fsync), so partial traces don't quietly look
  complete.
- **Validator enforces exactly one root per trace** — no accidental forest
  inside a single `trace_id`.
- **Tree walk is deterministic.** Siblings are ordered by `(started_ms,
  span_id)`, so two replays of the same recording print byte-identical trees.

## When to use

- Any agent mission that nests tool calls more than one level deep.
- Multi-agent orchestrations where sub-agents make their own tool calls.
- Hybrid stacks where vendor SDKs and your own code both want to log.

## When NOT to use

- Single-process, single-call missions where wall clock + PID is enough.
- Very high-rate (>100k spans/s/host) systems — at that volume you want
  OpenTelemetry SDK + a real collector, not this reference engine.

## Files

- `trace.py` — stdlib-only reference engine: `TraceContext`, `new_root`,
  `child`, `parse`, `Recorder`, `validate_records`, `render_tree`.
- `examples/01_nested_call.py` — root → 2 nested calls under one trace.
- `examples/02_orphan_and_malformed.py` — orphan span detection + parser
  rejection of mutated headers.

## Worked example 1 — root → 2 nested tool calls

```
$ python3 examples/01_nested_call.py
root header on the wire:
  v=1;trace=fe11b30a6aeeafe85caf4f21128dc434;span=c793ad7ca2d35c8d;parent=0000000000000000;flags=01

recorded spans (raw):
  {"attrs": {}, "duration_ms": 50, "ended_ms": 50, "name": "mission.run", "parent_span_id": "0000000000000000", "span_id": "c793ad7ca2d35c8d", "started_ms": 0, "status": "ok", "synthetic": false, "trace_id": "fe11b30a6aeeafe85caf4f21128dc434"}
  {"attrs": {"bytes_in": 512, "http_status": 200}, "duration_ms": 32, "ended_ms": 42, "name": "tool.fetch_user", "parent_span_id": "c793ad7ca2d35c8d", "span_id": "49d8e205c17a005e", "started_ms": 10, "status": "ok", "synthetic": false, "trace_id": "fe11b30a6aeeafe85caf4f21128dc434"}
  {"attrs": {"cache": "hit", "key_prefix": "u:42"}, "duration_ms": 3, "ended_ms": 18, "name": "tool.cache_lookup", "parent_span_id": "49d8e205c17a005e", "span_id": "f86f77a140895790", "started_ms": 15, "status": "ok", "synthetic": false, "trace_id": "fe11b30a6aeeafe85caf4f21128dc434"}

validation report:
  {"errors": [], "ok": true, "trace_count": 1}

tree view:
* mission.run [ok, 50ms] span=c793ad7c
  - tool.fetch_user [ok, 32ms] span=49d8e205
    - tool.cache_lookup [ok, 3ms] span=f86f77a1
```

Three calls, one shared `trace_id`, parent linkage `root → fetch_user →
cache_lookup`, validator green, tree walk reconstructs the nesting from the
flat record list.

## Worked example 2 — orphan span + malformed header

```
$ python3 examples/02_orphan_and_malformed.py
validation with one orphan:
{
  "errors": [
    {
      "code": "orphan_span",
      "parent_span_id": "d23f0824128b2f33",
      "span_id": "1818e811892f902b",
      "trace_id": "6513270e269e0d37f2a74de452e6b438"
    }
  ],
  "ok": false,
  "trace_count": 1
}

rejecting malformed headers:
  rejected: malformed trace header: 'v=1;trace=abc;span=def;parent=000;flags=01'
  rejected: malformed trace header: 'v=2;trace=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa;span=bbbbbbbbbbbbbbbb;parent=0000000000000000;flags=01'
  rejected: span id may not be all-zero
  rejected: span and parent must differ
```

The middle hop's process crashed before flushing its span; the validator
flags the leaf as `orphan_span` rather than letting the trace look complete.
Mutated headers (short hex, wrong version, zero span id, span equal to
parent) are rejected at parse time so the bad span never enters the
recorder.

## Integration sketch

```python
from trace import Recorder, child, new_root, parse

rec = Recorder()
root = new_root()  # at mission start
s = rec.open(root, "mission.run", started_ms=now_ms())

# When invoking a tool, hand it the child header:
ctx = child(root)
header = ctx.header()
result = call_tool(name="fetch_user", args=..., trace_header=header)
# inside call_tool:
#   sub_ctx = parse(trace_header)
#   sub_span = rec.open(sub_ctx, "tool.fetch_user", started_ms=now_ms())
#   ... do work ...
#   sub_span.finish("ok", ended_ms=now_ms(), **attrs)
```

## Composes with

- `agent-decision-log-format` — drop `trace_id` and `span_id` into the
  decision log so a single SQL `WHERE trace_id = ?` reconstructs the full
  story.
- `tool-call-retry-envelope` — every retry attempt is a synthetic child
  span (set `synthetic=True`); easy to filter out for cost reports.
- `agent-trace-redaction-rules` — `trace_id`/`span_id` are safe to
  passthrough; allowlist them as `string_short`.
- `tool-call-circuit-breaker` — circuit-trip events carry the offending
  span's `trace_id`, so a single failure in a fan-out is debuggable without
  log archaeology.
