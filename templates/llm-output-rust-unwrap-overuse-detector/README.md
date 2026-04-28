# llm-output-rust-unwrap-overuse-detector

## What it detects

Counts `.unwrap()` and `.expect(...)` calls inside Rust code fences
(```rust / ```rs) of an LLM-produced markdown document. Each occurrence
is reported with the fence index, line number within the fence, and the
matched snippet.

Also detects:

- `.unwrap_or_else(|_| panic!(...))` style escapes.

## Why it matters

`.unwrap()` and `.expect()` panic on `Err` / `None`. LLMs frequently
sprinkle them into example Rust code to avoid writing real error
handling, which is fine for a one-line example but dangerous in a
multi-function snippet a user might paste verbatim. Flagging this lets a
reviewer ask for `?` propagation, `match`, or `let ... else`.

Tests (`#[test]` functions) and `main()` examples sometimes legitimately
use `unwrap`; the detector still reports them so you can decide. Inline
comments and string literals are stripped before matching to avoid false
positives.

## How to use

```
python3 detector.py path/to/llm-output.md
```

Findings are printed one per line as:

```
fence#<idx> line<N>: <reason> -> <snippet>
```

The last line is always `total findings: <N>`. Exit code is `0`
regardless; this is informational.

The detector parses fenced code blocks; rust-looking code in inline
backticks or in non-rust fences is not scanned.
