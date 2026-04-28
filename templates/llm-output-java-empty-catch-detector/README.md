# llm-output-java-empty-catch-detector

## Purpose

Detect Java `catch` blocks whose body is completely empty — no
statements, no comments. Empty catch blocks silently swallow the
exception, destroying the stack trace and leaving the program in an
unknown state.

The legitimate "I genuinely want to ignore this" case is rare enough
that it should be marked with a comment explaining *why*. A
`catch (Foo e) { /* documented no-op */ }` is therefore not flagged —
the comment is the documentation that turns the silence from accident
into deliberate choice.

## Why LLMs emit empty catches

- The training corpus is full of tutorial code that ignores exceptions
  to keep the snippet short.
- When the model hits a checked-exception compile error, the cheapest
  "fix" is to wrap the call in `try { ... } catch (Exception ignored)
  {}` instead of fixing the actual cause.
- The model treats `try / catch` as a syntactic ritual ("Java requires
  this here") rather than a control-flow construct.

## When to use

- Reviewing LLM-generated Java (`.java`) before merging.
- Lint over an examples / scaffolding directory.
- Pre-commit lint on agent-authored Java code.

## How to run

```
python3 detect.py <file_or_dir> [<file_or_dir> ...]
```

Exit code is `1` if any findings, `0` otherwise. Findings print as
`path:line:col: empty-catch \u2014 <snippet>`.

## What it flags

- `empty-catch` — any `catch (...) { ... }` whose body, after stripping
  whitespace, contains *neither* a statement *nor* a comment.

## What it intentionally skips

- `catch` blocks containing any code (`log.warn(...)`, `throw new ...`,
  `return …`, etc.).
- `catch` blocks containing only a `//` or `/* */` comment — the
  comment is treated as documentation that the silence is deliberate.
- Occurrences of the literal text `catch (X e) {}` inside string
  literals or text blocks (`"""..."""`).

## Implementation notes

- Single-pass python3 stdlib scanner.
- String / char / text-block literals are blanked before regex matching,
  so the string `"catch (X e) {}"` does not trigger.
- Comments are *preserved* during blanking — the detector needs to look
  at the catch body to decide whether the silence is documented.
- Brace matching is comment-aware: a `}` inside `// ...` or `/* ... */`
  inside the catch body is not counted.

## Files

- `detect.py` — the detector (python3 stdlib only).
- `bad/` — three Java files that MUST trigger (6 empty catches total).
- `good/` — three Java files that MUST NOT trigger.
- `smoke.sh` — runs the detector and asserts bad-hits > 0 and
  good-hits == 0.

## Smoke output

```
$ bash smoke.sh
bad_hits=6
good_hits=0
OK: bad=6 good=0
```
