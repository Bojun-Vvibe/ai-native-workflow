# llm-output-scala-null-return-detector

## Purpose

Detect Scala methods that return `null` — either via an explicit
`return null` statement or by having `null` as the trailing expression
of the method body.

Scala provides `Option[T]` (`Some(x)` / `None`) precisely so that
absence is encoded in the type system. Returning a bare `null` from a
Scala method:

- Defeats the type system: `String` and `String | null` are not
  distinguished.
- Forces every caller into defensive `if (x == null)` checks (or worse,
  silent NPEs).
- Breaks composition with `map` / `flatMap` / `for`-comprehensions.
- Is widely flagged by linters (Scapegoat, WartRemover) as an
  anti-pattern.

LLMs love this pattern because:

- The training corpus has a lot of Java code where `null` is the
  conventional sentinel.
- "Return null on miss" is a one-token completion that is locally
  cheaper than introducing `Option`.
- The model often forgets that `Option`, `Either`, and `Try` exist
  unless prompted.

## When to use

- Reviewing LLM-generated Scala (`.scala`, `.sc`) before merging.
- CI lint over a sample / examples directory.
- Pre-commit lint on agent-authored Scala code.

## How to run

```
python3 detect.py <file_or_dir> [<file_or_dir> ...]
```

Exit code is `1` if any findings, `0` otherwise. Findings print as
`path:line:col: <kind> — <snippet>`.

## What it flags

- `return-null` — an explicit `return null` statement anywhere inside
  a `def` body.
- `trailing-null` — the last significant token of a `def` body is the
  bare identifier `null` (Scala-idiomatic implicit return of `null`).

## What it intentionally skips

- The literal word `null` inside `//` and `/* */` comments.
- The literal word `null` inside `"..."` strings, `"""..."""` triple
  strings, and char literals.
- `def` declarations whose body is a single expression without braces
  (`def f(x: Int) = x + 1`) — these are checked only if they happen to
  have a brace block.
- `Option[T]`, `Either`, `Try`, and other principled "absence" encodings.

The detector is line/regex based, not a full Scala parser; it errs
toward false negatives on heavily macro-driven or DSL-style code rather
than false positives on plain code.

## Files

- `detect.py` — the detector (python3 stdlib only).
- `bad/` — three Scala files that MUST trigger.
- `good/` — two Scala files that MUST NOT trigger.
- `smoke.sh` — runs the detector on `bad/` and `good/` and asserts
  bad-hits > 0 and good-hits == 0.

## Smoke output

```
$ bash smoke.sh
bad_hits=5
good_hits=0
OK: bad=5 good=0
```
