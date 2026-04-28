# llm-output-rust-unwrap-in-library-detector

Flags `.unwrap()` and `.expect(...)` calls in Rust **library** source
files. Both panic on `Err`/`None`, which converts a recoverable error
into a process-killing crash for every downstream caller of your crate.

## The smell

```rust
// src/cache.rs
pub fn get(&self, k: &str) -> String {
    let raw = std::fs::read_to_string(k).unwrap();   // <-- panics
    raw.lines().next().unwrap().to_string()          // <-- panics
}
```

A binary using your crate now aborts on a missing file or empty input
instead of returning a structured error.

## Why LLMs produce it

`.unwrap()` is the shortest path from "I have a `Result`" to "I have a
value", and it dominates training data because it appears in every
beginner Rust tutorial. When asked for "a Rust function that reads X",
an LLM that hasn't been pushed toward `?` propagation defaults to
`.unwrap()`. The resulting code looks idiomatic at a glance but is
fragile in any non-trivial caller graph.

## Scope

The detector intentionally does **not** flag:

- `fn main() { ... }` bodies — binaries can panic.
- Files named `main.rs`, `*_test.rs`, `*_tests.rs`.
- Files in any `tests/` directory (Cargo integration tests).
- Code inside `#[cfg(test)] mod ... { ... }` blocks (or `#[cfg(test)] fn ...`).
- `.unwrap()` / `.expect(...)` text appearing inside string literals
  (regular `"..."`, raw `r"..."`, raw with hashes `r#"..."#` /
  `r##"..."##`) or comments (`// ...`, `/* ... */`).

It **does** flag:

- `.unwrap()` chained off any expression (e.g. `x.foo().unwrap()`).
- `.expect("msg")` with any argument.
- Calls split across whitespace from the dot, e.g. `x . unwrap ( )`.

Stdlib only, single-pass scan per file.

## Usage

```
python3 detector.py <path> [<path> ...]
```

Paths may be files or directories. Directories are walked recursively
for `*.rs` files, skipping `.git`, `target`, and `node_modules`.

## Exit codes

| Code | Meaning |
| ---- | ------- |
| 0    | No hits |
| 1    | One or more hits printed |
| 2    | Usage error (no path given) |

## Sample run

```
$ python3 detector.py bad/
bad/config.rs:5: .expect() in library code: panics on Err/None
bad/config.rs:9: .unwrap() in library code: panics on Err/None
bad/config.rs:9: .unwrap() in library code: panics on Err/None
bad/lib.rs:5: .unwrap() in library code: panics on Err/None
bad/lib.rs:9: .expect() in library code: panics on Err/None
bad/service.rs:6: .unwrap() in library code: panics on Err/None
bad/service.rs:7: .unwrap() in library code: panics on Err/None
bad/helpers.rs:3: .unwrap() in library code: panics on Err/None
bad/helpers.rs:7: .unwrap() in library code: panics on Err/None
bad/parser.rs:4: .expect() in library code: panics on Err/None
bad/parser.rs:4: .expect() in library code: panics on Err/None
-- 11 hit(s)

$ python3 detector.py good/
-- 0 hit(s)
```

## Suggested fixes

- Return `Result<T, E>` and propagate with `?`.
- Use `.ok_or(MyError::Missing)?` to convert `Option` → `Result`.
- Use `.unwrap_or(default)` / `.unwrap_or_else(|| ...)` for known
  recoverable absences.
- Reserve `.expect("invariant: ...")` for genuinely-impossible cases,
  with the message documenting *why* it cannot happen.

## False-positive caveats

- A `lib.rs` that exposes a single `fn main()` (rare but legal in
  examples) will have `main` body skipped but unrelated `unwrap`s in
  the same file still flagged.
- Macro-generated `unwrap`s inside a hand-written macro definition are
  flagged because the detector does not expand macros.
- A `.unwrap` called as a free function from a path
  (`Option::unwrap(x)`) without the leading `.` is **not** flagged —
  this idiom is rare in LLM output.
