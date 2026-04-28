# llm-output-kotlin-not-null-assertion-detector

## Purpose

Detect Kotlin not-null assertion `!!` operator usages in LLM-generated Kotlin
code. The `!!` operator turns a nullable type `T?` into `T` by throwing
`NullPointerException` if the value is `null` — defeating Kotlin's
null-safety guarantee.

LLMs reach for `!!` to make `T?` types compile against APIs expecting `T`,
which is functionally equivalent to writing Java NPE-prone code in a language
designed to prevent exactly that.

## When to use

- Reviewing LLM-generated Kotlin snippets before merging.
- CI lint over `*.kt` / `*.kts` files in agent-authored modules where `!!`
  should require human justification.
- Pre-commit lint on agent-authored Android or backend Kotlin.

## How to run

```
python3 detect.py <file_or_dir> [<file_or_dir> ...]
```

Exit code is `1` if any findings, `0` otherwise. Findings print as
`path:line:col: <kind> — <snippet>`.

## What it flags

1. **Not-null assertion**: `foo!!`, `bar?.baz!!`, `map[k]!!`, `f()!!`.
2. **Chained not-null**: `foo!!.bar!!` — counted as two separate findings.
3. **Unsafe cast**: `as Foo` is allowed, but `value as Foo` followed by `!!`
   reports the `!!` (cast `as` itself is fine in Kotlin since it throws
   `ClassCastException` by design; the issue is the redundant `!!` after).

## What it intentionally skips

- Logical-not chains like `!!isReady` (double negation on a Boolean) — rare
  but legal; not the target of this detector. We match `!!` only when it
  follows an identifier, `)`, `]`, or `?`.
- `!!` inside a string literal or `//` comment.

## Files

- `detect.py` — the detector.
- `examples/bad.kt` — sample LLM output peppered with `!!`.
- `examples/good.kt` — same intent using `?.`, `?:`, `let`, `requireNotNull`.
