# `tool-call-timeout-laddered`

A **three-stage** timeout for agent tool calls — `soft` → `hard` →
`kill` — with explicit semantics at each stage. Pure stdlib, sync-only,
deterministic-ish (the runner is callback-based, not asyncio).

## What it solves

Most agent runtimes give a tool call **one** timeout. That forces a
binary choice on every dimension that matters:

- **Runaway vs. partial work.** If the timeout is generous, a stuck
  tool eats the orchestrator's deadline. If it's tight, useful partial
  results get thrown away the instant the timer fires.
- **Cooperative vs. forceful cancel.** A single timer can either
  politely ask the tool to stop (which a misbehaving tool can ignore)
  or yank the rug (which kills work that was about to checkpoint
  cleanly). It can't do both.
- **Process safety.** A tool blocked in a C extension or a syscall
  may not honor *any* Python-level cancel. Without a final hard kill,
  the orchestrator wedges forever.

The ladder gives each concern its own stage:

| Stage | Trigger | What happens |
|---|---|---|
| `soft_s` | Soft deadline elapsed | Tool is *signaled* to checkpoint and exit cleanly. It polls `should_soft_exit()` and returns its best partial result at a safe boundary. |
| `hard_s` | Hard deadline elapsed | Tool is considered cancelled. The orchestrator returns `outcome="hard_timeout"` with whatever the tool last `publish()`ed. The thread keeps running but is no longer awaited. |
| `kill_s` | Kill deadline elapsed | Final safety net. Returns `outcome="killed"`. The thread is daemon, so process exit is never blocked. |

## When to use

- Any tool whose work is **incrementally publishable** — paginated
  fetches, batch transforms, search-and-aggregate, multi-step
  refactors. The ladder lets you keep the pages/rows/files that
  finished even if the budget runs out.
- Any tool whose runtime is **bimodal** — usually fast, but
  occasionally hits a slow path (cold cache, network blip, large
  page) that you'd rather degrade than abort.
- Any orchestrator that **must not wedge** even if a single tool
  call is misbehaving.

## When NOT to use

- Tools that are atomic and side-effecting (a `POST`, a `git push`).
  There is no such thing as a useful "partial" — use a single hard
  timeout and a retry envelope (see
  [`tool-call-retry-envelope`](../tool-call-retry-envelope/)).
- Asyncio code paths. This runner uses a daemon thread because that's
  the only way to forcibly abandon a stuck blocking call without
  process-level signals. Async-native code should use
  `asyncio.wait_for` with cooperative checkpoints instead.
- Sub-second budgets. Polling overhead (~50ms) dominates; pick
  millisecond-level primitives.

## Anti-patterns this prevents

- **"One timeout for everything"** — the most common failure mode.
  Either too tight (lose partials) or too loose (orchestrator wedges).
- **"Timeout = throw away."** A timer firing should not erase work
  the tool already finished. The `partial` field survives every
  outcome including `killed`.
- **"Cooperative cancel only."** Without a hard stage, a tool that
  ignores `should_soft_exit()` (or is blocked in C code that can't
  check it) hangs the orchestrator forever.
- **"Kill via `Thread.join(timeout=...)` and pretend."** The thread
  keeps running and may corrupt shared state. The ladder makes the
  thread daemon and treats it as gone after `kill_s`.

## API

```python
from ladder import LadderConfig, run_with_ladder

cfg = LadderConfig(soft_s=2.0, hard_s=5.0, kill_s=7.0)

def my_tool(should_soft_exit, publish):
    results = []
    for page in fetch_pages():
        if should_soft_exit():
            publish({"results": results, "stopped_at": page.id})
            return {"results": results, "complete": False}
        results.append(process(page))
        publish({"results": results})         # checkpoint each loop
    return {"results": results, "complete": True}

r = run_with_ladder(my_tool, cfg)
# r.outcome ∈ {"ok", "soft_timeout", "hard_timeout", "killed", "error"}
# r.value   — tool's return value (None if it didn't return)
# r.partial — last published value (survives every outcome)
# r.elapsed_s, r.error
```

## Files

- `ladder.py` — reference runner. `python ladder.py demo` runs four canned cases.
- `example.py` — paginated-fetch worked example.

## Smoke test — `python3 ladder.py demo`

```
=== tool-call-timeout-laddered: demo ===

[1] cooperative-fast:
{
  "outcome": "ok",
  "value": {
    "answer": 42,
    "steps": 2
  },
  "partial": {
    "step": 1,
    "answer": 42
  },
  "elapsed_s": 0.0601,
  "error": null
}

[2] slow-cooperative (expect soft_timeout, partial preserved):
{
  "outcome": "soft_timeout",
  "value": {
    "completed": [
      0,
      1,
      4,
      9
    ],
    "early": true
  },
  "partial": {
    "completed": [
      0,
      1,
      4,
      9
    ],
    "stopped_at": 4
  },
  "elapsed_s": 0.2296,
  "error": null
}

[3] uncooperative (expect killed, partial='starting'):
{
  "outcome": "killed",
  "value": null,
  "partial": {
    "phase": "starting"
  },
  "elapsed_s": 0.6259,
  "error": "tool did not honor soft or hard deadline"
}

[4] tool-raises (expect error, partial preserved):
{
  "outcome": "error",
  "value": null,
  "partial": {
    "phase": "about to fail"
  },
  "elapsed_s": 0.0005,
  "error": "RuntimeError: simulated tool failure"
}
```

## Worked example — `python3 example.py`

A paginated tool fetches `N` pages at ~80ms each, under
`soft=0.30, hard=0.50, kill=0.70`.

```
=== worked example: paginated fetch under laddered timeout ===
config: soft=0.3s hard=0.5s kill=0.7s

--- A) 3 pages @ 80ms (fits in soft) ---
{
  "outcome": "ok",
  "value": {
    "page_count": 3,
    "complete": true
  },
  "partial": {
    "page_count": 3
  },
  "elapsed_s": 0.2689,
  "error": null
}

--- B) 12 pages @ 80ms (cooperative soft exit) ---
{
  "outcome": "soft_timeout",
  "value": {
    "page_count": 4,
    "complete": false
  },
  "partial": {
    "page_count": 4
  },
  "elapsed_s": 0.3565,
  "error": null
}

--- C) page-2 backend hang (hard timeout, partial = pages 0..1) ---
{
  "outcome": "killed",
  "value": null,
  "partial": {
    "page_count": 2
  },
  "elapsed_s": 0.7373,
  "error": "tool did not honor soft or hard deadline"
}
```

Read this carefully:

- **A** finished cleanly inside the soft budget; we got the full result.
- **B** ran past soft, the tool noticed via `should_soft_exit()` and
  returned 4 of 12 pages with `complete=False`. **No work was thrown
  away.**
- **C** hung in `time.sleep(60)` (a stand-in for a blocking C call
  that ignores Python-level cancel). Soft and hard both fired; the
  thread never returned; at `kill_s` the runner gave up. We still got
  `partial.page_count = 2` — the pages that finished before the hang.

The orchestrator is back in control in every case, in well under one
second, with the most useful answer the tool was able to produce.

## Tuning notes

- A reasonable starting ratio is `hard ≈ 1.5–2× soft` and
  `kill ≈ hard + (one polling interval × small constant)`. Too tight
  a gap between hard and kill defeats the purpose of having both.
- The 50ms internal polling cadence is the floor on responsiveness.
  Don't pick `soft_s < 0.1`.
- If your tool can publish very large partials, swap the in-memory
  `publish` for one that writes to disk — the ladder doesn't care
  what `publish` does, only that it's called.
