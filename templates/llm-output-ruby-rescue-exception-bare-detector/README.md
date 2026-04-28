# llm-output-ruby-rescue-exception-bare-detector

## Purpose

Detect Ruby exception handlers that swallow too much:

1. **Bare `rescue`** (no class given). In Ruby, `rescue` without a class
   is equivalent to `rescue StandardError`, which is fine in *some*
   cases — but the LLM-emitted version almost always pairs it with an
   empty body or a `nil` / `false` return, hiding real bugs.
2. **`rescue Exception`**. This catches `SystemExit`, `Interrupt`,
   `NoMemoryError`, `SignalException`, etc. — i.e. it eats Ctrl-C and
   makes the process unkillable. There is virtually never a legitimate
   reason for application code to do this; LLMs reach for it because
   "exception" feels like the most general / safest word.

Both patterns are extremely common in LLM output: the model sees a
test failing, wraps the call in `begin/rescue/end`, and considers the
problem solved.

## When to use

- Reviewing LLM-generated Ruby snippets before merging.
- CI lint over `*.rb` files in a sample/example directory.
- Pre-commit lint on agent-authored Ruby.

## How to run

```
python3 detect.py <file_or_dir> [<file_or_dir> ...]
```

Exit code is `1` if any findings, `0` otherwise. Findings print as
`path:line:col: <kind> — <snippet>`.

## What it flags

1. `rescue-exception` — any `rescue Exception` (with or without `=> e`,
   with or without trailing `then`). Always flagged.
2. `bare-rescue-empty` — a bare `rescue` (or `rescue =>` with no class
   list before the `=>`) whose body is empty or only `nil` / `false` /
   `next` / a comment, before the next `end` / `rescue` / `ensure` /
   `else`.
3. `inline-bare-rescue` — the inline form `expr rescue value`, which is
   always a bare rescue and is almost always wrong outside of one-liner
   scripts.

## What it intentionally skips

- `rescue SomeSpecificError` (named, narrow rescues).
- `rescue` inside a `# ...` line comment or a single/double-quoted string
  literal.

## Files

- `detect.py` — the detector (python3 stdlib only).
- `bad/` — five Ruby files that MUST trigger.
- `good/` — three Ruby files that MUST NOT trigger.
- `smoke.sh` — runs the detector and asserts bad-hits > 0, good-hits == 0.
