# llm-output-swift-force-unwrap-detector

## Purpose

Detect Swift force-unwrap (`!`) usages emitted by an LLM in generated Swift
code. Force-unwrap on optionals is a frequent source of runtime crashes
(`Fatal error: Unexpectedly found nil while unwrapping an Optional`) and is
almost always replaceable with `if let`, `guard let`, `??`, or optional
chaining.

LLMs love force-unwrapping because it makes generated code "compile and run on
the happy path" without dealing with the optional. That's the exact code that
crashes in production.

## When to use

- Reviewing LLM-generated Swift snippets before merging.
- CI lint over `*.swift` files in a sample/example directory where
  force-unwrap should be banned.
- Pre-commit lint on agent-authored iOS or server-side Swift.

## How to run

```
python3 detect.py <file_or_dir> [<file_or_dir> ...]
```

Exit code is `1` if any findings, `0` otherwise. Findings print as
`path:line:col: <kind> — <snippet>`.

## What it flags

1. **Force-unwrap of an identifier or call**: `foo!`, `bar.baz!`, `dict[k]!`,
   `f()!`, `try!`. Common LLM-emitted footguns.
2. **Forced cast**: `as!`. Same crash family as `!`.
3. **Implicitly-unwrapped-optional declaration**: `var x: Int!` /
   `let y: String!`. These crash on first read of `nil`.

## What it intentionally skips

- `!=` (not-equal operator).
- `!` as the prefix logical-not on a boolean (`!isReady`, `!(a && b)`).
- Trailing `!` inside a string literal or single-line `//` comment.

## Files

- `detect.py` — the detector.
- `examples/bad.swift` — sample LLM output with several force-unwraps.
- `examples/good.swift` — same intent, written safely.
