# llm-output-dart-late-init-detector

## Purpose

Detect Dart `late` field declarations that have **no initializer**.

`late` defers null-safety checks from compile time to *first read*. A
`late` field without an initializer is a runtime promise — "trust me,
I will assign this before anyone reads it." If the promise is wrong,
the program throws `LateInitializationError`, the exact NullPointer-
shaped failure that null safety was meant to eliminate.

The detector flags shapes like:

```
late String name;
late final ApiClient client;
late int total, retries;
```

It does NOT flag:

```
late final greeting = compute();   // lazy init pattern, OK
late final int n = expensive();    // lazy init with type, OK
final Foo foo = Foo();             // not late
String? nickname;                  // explicitly nullable, not late
```

## Why LLMs reach for `late`

- It "fixes" the compile error "non-nullable field must be initialized"
  faster than restructuring the constructor or making the field
  nullable.
- The model has seen `late` in Flutter `initState` patterns and
  overgeneralizes it to fields that should be plain `final` or
  nullable.
- The runtime cost (a hidden init check on every read) and the runtime
  failure mode (`LateInitializationError`) are invisible in the
  snippet, so the model treats it as a free fix.

## When to use

- Reviewing LLM-generated Dart / Flutter code (`.dart`) before merge.
- Lint over a samples / scaffolding directory.
- Pre-commit lint on agent-authored Dart code.

## How to run

```
python3 detect.py <file_or_dir> [<file_or_dir> ...]
```

Exit code is `1` if any findings, `0` otherwise. Findings print as
`path:line:col: late-no-init \u2014 <snippet>`.

## What it flags

- `late-no-init` — any `late` field declaration whose statement
  terminator is `;` (i.e. no `=` initializer).

## What it intentionally skips

- `late ... = expr;` — has an initializer (the legitimate lazy-init
  pattern).
- Plain `final` / nullable / unmodified declarations.
- The literal text `late ... ;` inside `//` or `/* */` comments and
  inside string literals (`'…'`, `"…"`, `'''…'''`, `"""…"""`).

## Implementation notes

- Single-pass python3 stdlib scanner.
- Comments and string / triple-string literals are blanked before regex
  matching (line numbers and length preserved).
- Regex captures the terminator character so the detector can cleanly
  distinguish "no init" (`;`) from "has init" (`=`).
- Method declarations (`late` cannot legally precede a method) are not
  matched because the regex requires a variable-name token followed by
  `;` or `=`.

## Files

- `detect.py` — the detector (python3 stdlib only).
- `bad/` — three Dart files that MUST trigger (5 declarations).
- `good/` — three Dart files that MUST NOT trigger.
- `smoke.sh` — runs the detector and asserts bad-hits > 0 and
  good-hits == 0.

## Smoke output

```
$ bash smoke.sh
bad_hits=5
good_hits=0
OK: bad=5 good=0
```
