# llm-output-csharp-async-void-detector

## Purpose

Detect C# methods declared `async void` that are NOT event handlers.
`async void` is a footgun: an exception thrown inside the body propagates
to the `SynchronizationContext` and typically crashes the process; the
caller has no `Task` to `await` and cannot `try/catch` it.

The only legitimate use of `async void` is an event handler with the
shape `(object sender, <SomethingDerivedFromEventArgs> e)`. Anything
else should be `async Task` (or `async Task<T>`).

LLMs love this pattern because:

- The signature looks "simpler" than `async Task`.
- The model has seen many event-handler examples in the training corpus
  and overgeneralizes the shape to non-handler methods.
- The compiler does not warn — the method compiles and "runs" until the
  first unobserved exception kills the process.

## When to use

- Reviewing LLM-generated C# (`.cs`) before merging.
- CI lint over a sample / examples directory.
- Pre-commit lint on agent-authored C# code.

## How to run

```
python3 detect.py <file_or_dir> [<file_or_dir> ...]
```

Exit code is `1` if any findings, `0` otherwise. Findings print as
`path:line:col: async-void — <snippet>`.

## What it flags

- `async-void` — any method declared `async ... void Name(<params>)`
  whose `<params>` does not match the two-parameter event handler shape
  `(<SomeType> <name>, <…>EventArgs <name>)`.

## What it intentionally skips

- Genuine event handlers `(object sender, EventArgs e)`,
  `(object s, RoutedEventArgs e)`, `(object s, MouseEventArgs e)`, etc.
- `async Task` and `async Task<T>` declarations.
- Sync `void` methods.
- Mentions of `async void` inside `//` or `/* */` comments and inside
  string / verbatim / interpolated string literals.

The detector is line/regex based, not a full C# parser; it errs toward
false negatives on heavily preprocessor-driven code rather than false
positives on plain code.

## Files

- `detect.py` — the detector (python3 stdlib only).
- `bad/` — three C# files that MUST trigger.
- `good/` — two C# files that MUST NOT trigger.
- `smoke.sh` — runs the detector on `bad/` and `good/` and asserts
  bad-hits > 0 and good-hits == 0.

## Smoke output

```
$ bash smoke.sh
bad_hits=5
good_hits=0
OK: bad=5 good=0
```
