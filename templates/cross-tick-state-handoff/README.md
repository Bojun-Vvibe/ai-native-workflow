# `cross-tick-state-handoff`

A file-locked, atomic JSON state envelope for handing partial work
between successive ticks of an autonomous dispatcher (or any
cron-like loop). Solves three failure modes that "just write a JSON
file" gets wrong:

1. A torn write from a crash mid-`json.dump`.
2. Two ticks racing because the previous one ran long.
3. A reader silently consuming an envelope it doesn't understand.

## The problem

You have a long-running daemon that wakes up every N minutes,
considers what to do this tick, runs some work, and goes back to
sleep. Each tick needs to know what the *previous* tick did so it
can avoid repeating work, respect rolling budgets, advance a queue
position, or mark a mission as complete.

The naive solution is to `json.dump` a dict to a file at the end of
each tick and `json.load` it at the start of the next. That works
right up until one of three things happens:

  - **Crash mid-write.** The OS kills the process between `open(path,
    "w")` (which truncates) and `json.dump` finishing. The next tick
    starts up, opens a zero-byte or half-written file, and crashes
    on `json.JSONDecodeError`. Now the daemon is wedged — and worse,
    it's wedged in a state where every retry has the same outcome.
  - **Tick overlap.** A tick takes longer than the wake-up interval.
    The next tick fires while the previous one is still computing
    its commit. They both write to the same path. Whichever one
    `os.replace`s last wins; the other tick's work is silently lost,
    or — without `os.replace` — you get an interleaved file.
  - **Schema drift.** You ship a new version of the daemon that
    expects an extra field. It reads the old envelope, doesn't find
    the field, and either crashes deep inside business logic or
    (worse) silently treats `None` as "zero" and restarts a queue
    from the top.

This template addresses all three with one small surface.

## The bug class it prevents

Silent state loss. Every issue this template guards against can be
diagnosed only by noticing that the *behavior* of the daemon is
wrong — there's no exception, no log line, no metric spike. The
crash-mid-write case looks like "the daemon forgot what it was
doing." The tick-overlap case looks like "we processed mission X
twice this hour." The schema-drift case looks like "the daemon is
suddenly making decisions like it just started." Those are the
worst kind of bugs to debug because the data the daemon is acting
on already looks wrong by the time you look at it.

## Approach

`HandoffStore(path, schema_version)` wraps three POSIX primitives:

  1. **`fcntl.flock` on a sibling `.lock` file** for cross-process
     mutual exclusion. The lock is held only across the
     read-modify-write sequence, never across user code outside the
     `with` block.
  2. **`tempfile.mkstemp` + `os.replace`** for atomic commits. The
     write goes to a temp file in the same directory as the
     envelope; only after `fsync` does `os.replace` swap it into
     place. POSIX guarantees `os.replace` is atomic on the same
     filesystem.
  3. **A `_schema` field at the top of the envelope** that the
     reader checks before unwrapping. A mismatch raises
     `HandoffError` immediately — never silently degrades.

The public API is one class:

```python
store = HandoffStore("/var/lib/myapp/state.json", schema_version=1)

# Read-only:
state = store.snapshot()  # dict | None

# Read-modify-write under lock:
with store.transaction() as state:
    state.setdefault("tick_count", 0)
    state["tick_count"] += 1
    # commit happens automatically on clean __exit__
```

If the body of the `with` block raises, the envelope is **not**
modified — the temp file is unlinked and the lock is released.

## Contract

| Property | Guarantee |
|---|---|
| Atomic commit | Either the new envelope is fully visible or the old one is. No torn reads, ever. |
| Crash-safe | A SIGKILL between `transaction.__enter__` and `__exit__` leaves the previous envelope intact. |
| Cross-process safe | Two processes calling `transaction()` on the same path serialize via `flock`. |
| Schema-pinned | Reader refuses an envelope whose `_schema` doesn't match `schema_version`. |
| Lock-timeout-bounded | `transaction(lock_timeout_s=...)` raises `HandoffError` rather than blocking forever. |
| Stdlib-only | No third-party deps. Works anywhere Python 3.9+ runs on POSIX. |

## When to use this

- Cron jobs / launchd agents that need to remember anything between runs.
- Autonomous agent dispatchers passing partial mission state between ticks.
- Single-host queue offset trackers.
- Anything where you'd otherwise reach for SQLite "just for one row."

## When NOT to use this

- Multi-host coordination. `flock` is local. Use a real KV store
  (etcd, consul, redis with redlock) for that.
- High-write-rate state (>10/sec). The lock + fsync round-trip is
  ~1ms; that's fine for a tick-sized loop, wasteful for a hot path.
- Anything that needs partial-update semantics. This template
  read-modify-writes the whole envelope every commit.

## Integration notes

- The directory containing the envelope is created on construction
  (`exist_ok=True`). The lock file lives alongside, named
  `<path>.lock`. Both should be on the same filesystem as `path` so
  `os.replace` stays atomic.
- `schema_version` is an integer. When you ship a breaking schema
  change, bump it and add a migration that reads the old version
  manually before constructing the new `HandoffStore`.
- `transaction()` defaults to a 5-second lock timeout, which is
  long enough for an honest in-flight tick to finish but short
  enough to fail fast if a previous tick deadlocked. Tune per app.
- Pair with `agent-checkpoint-resume` for *intra-tick* progress
  (resuming a single long-running tick after restart) — this
  template covers *inter-tick* state, which is a different problem.

## Worked example output

Running `python3 examples/run.py` (stdlib only, no setup):

```
tick 0: no prior envelope (clean start)
tick 1: count=1 last=1 mission='templates'
tick 2: count=2 last=2 mission='missions'
tick 3: count=3 last=3 mission='oss'
tick 4: count=4 last=4 mission='templates'
final history has 4 entries
caught simulated crash: simulated mid-tick crash
crash-safety: envelope unchanged after exception (OK)
schema guard fired: envelope schema version 1 does not match expected 2; refusing to load. Migrate the envelope or bump the reader.
ALL CHECKS PASSED
```

The example simulates four successive dispatcher ticks, then proves
crash-safety by raising inside `transaction()` and confirming the
envelope is unchanged, then proves the schema guard by trying to
load with `schema_version=2` against an envelope written at version 1.
