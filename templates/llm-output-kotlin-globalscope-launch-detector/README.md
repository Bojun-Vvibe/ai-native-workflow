# llm-output-kotlin-globalscope-launch-detector

## What it detects

Uses of `GlobalScope.launch`, `GlobalScope.async`, `GlobalScope.future`,
`GlobalScope.actor`, and `GlobalScope.produce` inside Kotlin code
fences (```kotlin / ```kt / ```kts) of an LLM-produced markdown
document.

## Why it matters

`GlobalScope` is an unbounded, application-lifetime CoroutineScope.
Coroutines launched from it:

- are NOT tied to the lifecycle of any caller — they keep running after
  the calling Activity / ViewModel / request handler is gone, leaking
  resources and (on Android) crashing on stale references;
- swallow exceptions silently unless you wrap them in a
  `CoroutineExceptionHandler`, because there is no parent to propagate
  to;
- defeat structured concurrency, so `coroutineScope { ... }` and
  `supervisorScope { ... }` cancellation cannot reach them.

LLMs reach for `GlobalScope.launch { ... }` because it is the shortest
"just run this in the background" snippet. Production code should
almost always use a real scope: `viewModelScope`, `lifecycleScope`,
the injected `CoroutineScope`, or a `coroutineScope { ... }` block.

The Kotlin team explicitly marked `GlobalScope` as
`@DelicateCoroutinesApi` to discourage it.

## False-positive notes

- Bare `launch { ... }` and `async { ... }` are NOT flagged — those are
  members of an enclosing `CoroutineScope` and are typically fine.
- Mentions of `GlobalScope` inside string literals, character literals,
  triple-quoted strings, and `//` line comments are stripped before
  matching.
- A trailing `// llm-detector: allow GlobalScope` comment on the same
  line suppresses the finding for that line. Use sparingly — usually
  only legitimate at `main()` in a CLI tool.
- The detector does not currently track `@OptIn(DelicateCoroutinesApi::class)`
  scopes; it always flags. Add a suppression comment if you have
  consciously opted in.

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

`bad.md` has 5 distinct GlobalScope-receiver usages.
`good.md` shows the same logic via structured scopes plus one
suppressed `main()` bridge.
