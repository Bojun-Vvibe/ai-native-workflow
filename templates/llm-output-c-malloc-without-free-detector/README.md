# llm-output-c-malloc-without-free-detector

## Purpose

Detect C functions that allocate heap memory via `malloc` / `calloc` /
`realloc` / `strdup` and return normally without ever calling `free` on the
allocation (and without returning ownership to the caller). This is the
classic "leak on the happy path" footgun.

LLMs love this pattern because:

- The generated code "works" — it compiles, runs once, returns the right
  answer, and only leaks under repeated calls or long-running processes.
- The model often forgets the cleanup branch on early `return` paths after
  it has already shown the allocation.
- Tutorials in the training corpus frequently omit `free` for brevity, so the
  model statistically reproduces the same omission.

## When to use

- Reviewing LLM-generated C snippets before merging.
- CI lint over `*.c` / `*.h` files in a sample/example directory.
- Pre-commit lint on agent-authored systems code.

## How to run

```
python3 detect.py <file_or_dir> [<file_or_dir> ...]
```

Exit code is `1` if any findings, `0` otherwise. Findings print as
`path:line:col: <kind> — <snippet>`.

## What it flags

For each function body, the detector pairs heap allocations against
disposition:

1. `leak-no-free` — local pointer is assigned from `malloc` / `calloc` /
   `realloc` / `strdup` and the function returns without `free(p)`,
   without returning `p`, and without storing `p` into an out-parameter
   (`*out = p;`) or a struct field reachable from a parameter.
2. `realloc-leak-on-fail` — `p = realloc(p, n);` overwrites the original
   pointer with `NULL` on failure, leaking the old buffer. Use a temp.

## What it intentionally skips

- Allocations inside a single-line `//` comment or `/* ... */` comment.
- Allocations inside a string literal.
- Functions that have any `return <ptr>;` of the allocated identifier
  (caller-owns convention).
- Functions that contain `free(<ptr>)` anywhere in the body.

The detector is line/regex based, not a full C parser; it errs toward
false negatives on heavily macro-ized code rather than false positives on
plain code.

## Files

- `detect.py` — the detector (python3 stdlib only).
- `bad/` — five C files that MUST trigger.
- `good/` — three C files that MUST NOT trigger.
- `smoke.sh` — runs the detector on `bad/` and `good/` and asserts
  bad-hits > 0 and good-hits == 0.
