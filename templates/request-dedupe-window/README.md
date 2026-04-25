# request-dedupe-window

## Problem

The same logical request keeps arriving in quick succession — a retry loop fires before the original response lands, a user double-clicks, an agent loops on a partial trace and re-emits the same call. You want to forward the *first* one and suppress the rest until enough time has passed that the next one is genuinely a new request, not a duplicate of the one you already accepted.

Doing this with an unbounded `set` of seen requests leaks memory. Doing it with an LRU of fixed size silently re-allows duplicates once the set churns. The right primitive is a *sliding-window* gate keyed by request identity, where every entry expires `window_seconds` after the *first* time it was seen.

## When to use

- In front of an expensive or non-idempotent call (`POST /v1/charge`, model invocation, write to an external system) where re-firing the same request inside a short window is almost always a bug, not an intent.
- As a small in-process gate alongside a real durable idempotency store (`tool-call-idempotency-key`) — this catches the cheap, fast cases without a round-trip.
- When you need *temporal* dedup, not permanent dedup. The same key should be allowed through again after enough quiet time.

## When NOT to use

- You need durable, cross-process, cross-restart idempotency. Use `tool-call-idempotency-key` / `tool-call-retry-envelope` with a SQLite or DB-backed store.
- The dedup decision needs the response body (e.g. "suppress only if the previous one succeeded"). This template has no notion of outcomes.
- You want permanent content-addressed caching of results. Use `tool-result-cache`.

## API sketch

```python
from template import RequestDedupeWindow

def key_fn(req):
    return f"{req['method']}:{req['path']}"

dq = RequestDedupeWindow(window_seconds=5.0, key_fn=key_fn)

decision = dq.submit(request)
if decision.verdict == "forward":
    response = do_the_thing(request)
else:
    log.info(
        "duplicate request suppressed",
        extra={"key": decision.key, "age_s": decision.age_s,
               "suppressed_count": decision.suppressed_count},
    )
```

Invariants:

- For each key, the *first* `submit` (or first after the window has elapsed) returns `verdict="forward"` and `suppressed_count=0`.
- Subsequent `submit`s of the same key inside the window return `verdict="suppress"`, `age_s` measured from the original, and a monotonically increasing `suppressed_count`.
- A `submit` after `window_seconds` of quiet *resets* the entry: forwards again, count back to zero.
- `sweep()` is optional — `submit` already lazily expires entries on access; `sweep()` exists for callers who want to bound memory between bursts.
- `now_fn` is injectable for deterministic tests; production uses `time.monotonic`.

## Worked example invocation

```
python3 templates/request-dedupe-window/worked_example.py
```

## Failure modes covered by the design

- **Memory leak from unbounded "seen" set**: lazy expiry on submit + `sweep()` keep the working set proportional to the live, in-window key count.
- **Wrong-after-LRU-churn dedup**: this is timestamp-based, not capacity-based — churn does not weaken the gate.
- **Read-extends-window trap**: reads do not extend the window; the entry expires `window_seconds` after the *original* observation, period.
- **Bad key function**: `key_fn` returning a non-string or empty string raises `ValueError` on the offending submit so the bug surfaces at the first call, not in production traces a week later.
- **Non-deterministic clocks in tests**: `now_fn` injection is mandatory for the test suite to work.

## Composition notes

- Pair with `tool-call-idempotency-key` — this template is the cheap front line, the idempotency-key store is the durable backstop.
- Pair with `agent-decision-log-format` — log every `verdict="suppress"` with `key`, `age_s`, and `suppressed_count` so a flapping caller is visible in the trace.
- Pair with `structured-error-taxonomy` — a `suppress` verdict is *not* an error and should not be classified as `transient` / `permanent`; it is a deliberate gate decision.
