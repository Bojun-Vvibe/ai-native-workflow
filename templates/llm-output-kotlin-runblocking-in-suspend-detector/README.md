# llm-output-kotlin-runblocking-in-suspend-detector

Flags `runBlocking { ... }` invocations that appear inside the body of
a `suspend fun` in Kotlin sources.

## The smell

```kotlin
suspend fun fetchUser(id: Long): String {
    return runBlocking {           // <-- already in a coroutine!
        delay(50)
        "user:$id"
    }
}
```

The whole point of `suspend fun` is non-blocking suspension. Calling
`runBlocking` from inside one parks the calling thread on a coroutine
that the suspend machinery would have happily awaited for free —
turning a cooperative, scalable call into a thread-blocking one.

On a UI dispatcher this freezes the foreground. On a small server
dispatcher (`Dispatchers.IO` defaults to ~64 threads, `Default` to
the CPU count) a few of these in flight will exhaust the pool and
deadlock the entire process.

## Why LLMs produce it

`runBlocking` is the most-cited coroutine entry point in tutorials
and "hello world" snippets, because it is the canonical bridge from
blocking `main` into coroutine-world. When the model is asked to make
an existing function async, it adds `suspend` to the signature but
keeps the `runBlocking` body it already had — neglecting that the
two cancel each other out. The bounded fixes (`withContext`,
`coroutineScope`, `async { ... }.await()`) are less prominent in
training data.

## How the detector works

Single-pass per-line scanner over `.kt` / `.kts` files:

1. **Mask comments and string literals.** Block (`/* */`), line (`//`),
   double-quoted, single-quoted (Char), and triple-quoted raw strings
   are replaced with spaces so that `runBlocking` mentioned in docs or
   strings does not trigger.
2. **Track scope stack.** Every `fun` declaration is queued as a
   "pending fun scope" with a `suspend` flag (set if the same line
   contains `suspend` before `fun`). The flag is bound to the next
   `{`. Plain `{` pushes a `block` scope. `}` pops.
3. **Flag `runBlocking`** whose nearest enclosing `fun` scope has the
   suspend flag set.

Stdlib only.

## False-positive caveats

- **Suspend lambdas.** A `suspend () -> T` lambda body is not detected
  as suspending — only `suspend fun` declarations are. A `runBlocking`
  inside such a lambda passed to a suspend builder will not trigger
  (false negative). In practice this is rare in LLM output.
- **Multi-line `fun` signatures** where the `suspend` modifier appears
  on a different line than `fun` will be missed (the detector pairs
  them per-line). Use single-line modifiers `suspend fun ...` (the
  Kotlin-idiomatic form) and this is a non-issue.
- **`suspend`-annotated function types in parameter lists** — e.g.
  `fun apply(block: suspend () -> Int)` — contain `suspend` before
  `fun`'s parameter list closes. The detector binds suspend on the
  *line containing* `fun` to that fun, so this declaration would be
  treated as a suspend fun. If your codebase uses this pattern often,
  add a `// nolint: runblocking-in-suspend` upstream of the scanner.
- The detector is syntactic and does not know whether the
  `runBlocking` is a `kotlinx.coroutines.runBlocking` or a same-named
  utility from another package. Callers shadowing the standard name
  will produce false positives — uncommon in real code.

## Usage

```
python3 detector.py path/to/kotlin/project
```

Exit code `0` if no hits, `1` if any.

## Smoke test

See `SMOKE.md`. Current counts: `bad/` = 7 hits across 6 files,
`good/` = 0 hits across 6 files.
