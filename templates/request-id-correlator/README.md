# request-id-correlator

In-process correlation-id propagation primitive for **stdlib `logging`** so
every log line emitted by any nested helper, async coroutine, or worker
thread automatically carries the same request id — without threading the id
through function signatures.

The wire format (W3C-traceparent, B3, `X-Request-Id`) is the caller's job.
This template owns the *in-process* substrate that turns "id arrived in the
HTTP header" into "every log line under this request is queryable on
`correlation_id=<id>`."

| Bug class | What ad-hoc code does | What this correlator does |
|---|---|---|
| Logger filter on the wrong target | Filter attached to a logger doesn't fire on records propagated up from child loggers | `install_logging_filter` accepts both `Logger` and `Handler`; attaching to a HANDLER catches every record the handler sees |
| Background `asyncio.create_task` outside any request | Task runs forever with `correlation_id=None` and emits records the log query silently misses | `spawn_task` raises `RuntimeError` when called outside an active `request_scope` (opt-out via `require_context=False`) |
| `executor.submit(fn)` loses ContextVars across thread boundary | Worker thread sees `current_id() is None`, log line stamped `<orphan>` | `submit_with_context(executor, fn, ...)` snapshots `contextvars.copy_context()` and runs `fn` inside it |
| `correlation_id is null` queries silently miss orphan records | `record.correlation_id` left unset; SQL filter on `IS NULL` matches both "never stamped" and "explicitly absent" | Every record gets a string value: real id or the literal `"<orphan>"` sentinel |
| `request_id=""` accepted as valid | An upstream sending an empty `X-Request-Id` poisons every downstream join | `enter_request("")` raises `ValueError` immediately |

## Problem

The W3C `traceparent` header solves the *cross-process* part. The *in-process*
part — getting that id onto every log line emitted by every helper between
the request handler and the database driver — is consistently solved by
ad-hoc plumbing through function signatures, which:

1. Decays the moment a refactor adds a new layer.
2. Breaks at every `await` point unless a vendor framework patches it.
3. Breaks at every `executor.submit` call unless the caller remembers to
   wrap it.
4. Silently emits orphan log lines from background tasks the operator
   never realized were running.

`contextvars.ContextVar` is the Python primitive that fixes (1) and (2) —
PEP 567 made it inherit across `await` and into `asyncio.create_task`. This
template wraps it with the four properties ad-hoc usage gets wrong.

## When to use

- Any service or agent process where logs from multiple call frames /
  async tasks / worker threads need to be joinable on a per-request id.
- Anywhere you'd otherwise pass a `request_id` parameter through five
  function signatures.
- Background processors that *should* always run inside a request context
  and need a loud failure when they don't.

## When NOT to use

- Cross-process tracing — use a wire-format propagator
  (`tool-call-trace-id-propagator` for the W3C-traceparent shape).
- Span / parent-span trees — that's a richer model. Use OpenTelemetry, or
  `tool-call-trace-id-propagator` if you only need `(trace, span, parent)`
  triples.
- Single-threaded scripts where you can pass the id explicitly without
  pain.

## How it composes

- **`tool-call-trace-id-propagator`**: that one carries `(trace, span,
  parent)` across the wire. This one stamps `trace` onto every log line
  inside one process. They compose: parse the inbound header → call
  `enter_request(parsed.trace_id)` → every log line in scope is joinable
  with the upstream service's logs.
- **`agent-decision-log-format`**: the eight required fields include
  `mission_id`. Use `enter_request(mission_id)` at mission start and the
  decision log lines auto-stamp `correlation_id == mission_id`.
- **`agent-trace-redaction-rules`**: redactor reads
  `record.correlation_id` (set by this filter) to scope per-mission
  redaction policies.
- **`structured-log-redactor`**: orthogonal — that one redacts *values*
  inside a record's message, this one stamps *one extra field* onto every
  record. Run both filters; ordering doesn't matter.

## Public API

```python
from correlator import (
    request_scope, enter_request, leave_request,
    current_id, install_logging_filter,
    spawn_task, submit_with_context,
    ORPHAN_SENTINEL,
)

# At service / handler entry point:
install_logging_filter()  # attach to root logger
# OR (preferred — runs for ALL records this handler sees):
install_logging_filter(my_handler)

# Per-request:
with request_scope(inbound_header_request_id) as rid:
    log.info("processing")             # auto-stamped with rid
    helper_function()                  # also auto-stamped, no plumbing
    task = spawn_task(do_async_work()) # task inherits rid
    fut  = submit_with_context(executor, do_thread_work)  # cross-thread

# Outside any scope:
log.info("background")                 # stamped with "<orphan>"
```

## Worked example

`worked_example.py` runs five scenarios in one process, capturing every
emitted log record into an in-memory handler so the assertions are
deterministic.

### Verified output

The bound id in Scenario 1 is a fresh CSPRNG value (`secrets.token_hex(8)`)
and changes on every run — every other field is stable.

```
================================================================
Scenario 1: basic — request_scope binds id, nested helper logs it
================================================================
  bound id: 74541c9af2e128a8
  [74541c9af2e128a8] entered request
  [74541c9af2e128a8] helper sees id=74541c9af2e128a8

================================================================
Scenario 2: orphan — log line outside any scope gets '<orphan>'
================================================================
  [<orphan>] emitted before any request_scope

================================================================
Scenario 3: async — spawn_task propagates id, outside-scope raises
================================================================
  outer scope bound id: upstream-abc-123
  worker saw id:       upstream-abc-123
  [upstream-abc-123] about to spawn task
  [upstream-abc-123] async worker sees id=upstream-abc-123
  spawn_task outside scope correctly raised: RuntimeError

================================================================
Scenario 4: thread — submit_with_context vs bare submit
================================================================
  bound id: req-thread-xyz
  with_context: req-thread-xyz
  bare_submit: <none>
  [req-thread-xyz] with_context thread sees id=req-thread-xyz
  [<orphan>] bare_submit thread sees id=<none>

================================================================
Scenario 5: custom id — honor upstream X-Request-Id
================================================================
  bound id: inbound-header-deadbeef0001
  log line stamped with: inbound-header-deadbeef0001

All scenarios passed.
```

### What each scenario proves

- **Scenario 1** — auto-injection. A `helper_function` three call frames
  deep gets the same id stamped on its log line as the entry point, with
  zero parameter plumbing. The id appears in the message body
  (`helper sees id=…`) AND in the structured `correlation_id` field —
  proving the ContextVar is observable in user code as well as the filter.
- **Scenario 2** — orphan detection. A log line emitted before any
  `request_scope` ever opened gets `<orphan>` (literal string), not
  `None`. Log queries on `correlation_id == "<orphan>"` find these;
  queries on `correlation_id IS NULL` would silently miss them.
- **Scenario 3** — async. `spawn_task` correctly propagates the id into
  the new task (proven by both the captured log line and the worker's
  return value). The same call OUTSIDE any scope raises `RuntimeError`
  loudly — this is the loud-failure property that catches the most common
  bug ("background task spawned at module load, runs forever with no
  correlation").
- **Scenario 4** — thread. The exact same scope and the exact same worker
  function: `submit_with_context` propagates the id (`req-thread-xyz`),
  bare `executor.submit` does NOT (`<none>` in the worker, `<orphan>` on
  the log line). This is the side-by-side proof that the wrapper is not
  cosmetic.
- **Scenario 5** — custom id. An upstream-supplied id
  (`inbound-header-deadbeef0001`) is honored verbatim instead of replaced
  by a freshly minted one. This is the path that stitches a per-process
  correlator onto an inbound `X-Request-Id` header.

## Run it

```bash
python3 worked_example.py
```

## Adapt this section

When you copy this template into your own repo, adjust:

- The id minter. Default is `secrets.token_hex(8)` (16 hex chars). If
  your wire format is W3C-traceparent, mint a 32-hex `trace_id` and
  pass it to `enter_request(trace_id)` — the correlator never invents
  an id when one is supplied.
- The logging integration point. Attach the filter to whichever
  `Handler` your application configures (file, stream, JSON, syslog).
  Filters on a handler fire for every record the handler sees,
  including records propagated up from child loggers — which is almost
  always what you want.
- The orphan sentinel. Default is the literal string `"<orphan>"`. If
  your log pipeline uses a different sentinel, edit `ORPHAN_SENTINEL`
  in `correlator.py` and your log queries together.
- The `spawn_task` policy. The default raises on out-of-scope spawns
  because that catches the most common bug. If your service legitimately
  spawns long-lived background tasks at module load, use
  `spawn_task(..., require_context=False)` and accept the orphan log
  lines as the audit trail.
