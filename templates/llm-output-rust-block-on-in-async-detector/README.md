# llm-output-rust-block-on-in-async-detector

## What it detects

Calls to synchronous executors (`block_on`) made from inside an `async`
context in Rust code fences (```rust / ```rs) of an LLM-produced
markdown document.

Patterns flagged inside an `async fn` body or `async { ... }` /
`async move { ... }` block:

- `futures::executor::block_on(...)`
- `tokio::runtime::Handle::current().block_on(...)`
- `Handle::current().block_on(...)`
- `Runtime::new()...block_on(...)`
- any `.block_on(` method call (heuristic — covers `rt.block_on(fut)`)
- bare `block_on(...)` (heuristic — common when imported as an alias)

Each finding is reported with fence index, line number within the
fence, a human-readable reason, and the matched snippet.

## Why it matters

`block_on` runs a future to completion on the current thread,
synchronously. Calling it from inside an `async` function:

- panics on the multi-thread tokio runtime ("Cannot start a runtime
  from within a runtime"), OR
- deadlocks the current-thread runtime, because the only worker is now
  parked waiting on the inner future to make progress.

LLMs frequently produce this pattern when they confuse "run a future"
(`block_on`) with "wait for a future" (`.await`). The fix is almost
always to replace the `block_on(fut)` with `fut.await`, or to push the
synchronous bridge to the very edge of the program (the bin entrypoint).

## False-positive notes

- Calls outside any `async` region (e.g. inside `fn main()` calling
  `rt.block_on(async { ... })`) are intentionally NOT reported. That is
  the correct place to bridge sync->async.
- The async-region tracker uses brace counting on text with comments
  and string literals stripped; deeply nested macros that emit
  unbalanced braces inside string literals could confuse it. In
  practice this is rare in LLM output.
- Identifiers inside string literals or `//` line comments are stripped
  before matching to avoid false hits (e.g. prose mentioning
  `block_on` in a doc comment is ignored if scrubbing succeeds).
- The bare `block_on(` heuristic does match `my_block_on(` if not
  preceded by an identifier / `:` / `.` — it is anchored with a
  negative look-behind to avoid that case.

## How to use

```
python3 detector.py path/to/llm-output.md
```

Findings are printed one per line as:

```
fence#<idx> line<N>: <reason> -> <snippet>
```

The last line is always `total findings: <N>`. Exit code is `0`
regardless; this is informational so it can be wired into a soft gate.

## Worked example

```
python3 detector.py examples/bad.md
python3 detector.py examples/good.md
```

`bad.md` contains 5 distinct flagged patterns inside async contexts.
`good.md` contains the same APIs used correctly (only at the sync edge,
or replaced with `.await`).
