# llm-output-haskell-unsafe-performio-detector

## Purpose

Detect call sites of `unsafePerformIO` (and friends) in Haskell code.

`unsafePerformIO :: IO a -> a` lets you smuggle an `IO` action into a
pure context. It has a small number of legitimate uses (lazy global
caches, FFI wrappers with proven idempotence) but in LLM-generated
Haskell it usually appears because the model wanted to "just print
something" or "just read a file" inside what was supposed to be a
pure function. The cost: silent loss of referential transparency,
non-deterministic evaluation order, and `seq`/`bang`-pattern hazards.

Sibling escape hatches caught here:

- `unsafeDupablePerformIO`
- `unsafeInterleaveIO`
- `accursedUnutterablePerformIO` (bytestring-internal)

## When to use

- Reviewing LLM-generated Haskell snippets before merging.
- CI lint over `*.hs` / `*.lhs` files in a sample/example directory.
- Pre-commit lint on agent-authored Haskell.

## How to run

```
python3 detect.py <file_or_dir> [<file_or_dir> ...]
```

Exit code is `1` if any findings, `0` otherwise. Findings print as
`path:line:col: <kind> \u2014 <snippet>`.

## What it flags

- `unsafe-unsafePerformIO`
- `unsafe-unsafeDupablePerformIO`
- `unsafe-unsafeInterleaveIO`
- `unsafe-accursedUnutterablePerformIO`

… anywhere outside a comment / string literal / `import` line.

## What it intentionally skips

- `import System.IO.Unsafe (unsafePerformIO)` — the import itself is
  not a use site. Re-exports from the same module still don't run code.
- Mentions inside `-- line comments`, `{- block comments -}`, or
  `"string literals"`.

## Files

- `detect.py` — the detector (python3 stdlib only).
- `bad/` — five Haskell files that MUST trigger.
- `good/` — three Haskell files that MUST NOT trigger.
- `smoke.sh` — runs the detector and asserts bad-hits > 0, good-hits == 0.

## Example output

```
$ python3 detect.py bad/
bad/01_global_counter.hs:7:14: unsafe-unsafePerformIO \u2014 counter = unsafePerformIO (newIORef 0)
...
# 6 finding(s)
```
