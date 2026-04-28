# llm-output-ocaml-obj-magic-detector

## Purpose

Detect call sites of OCaml `Obj.magic` (and the rest of the unsafe
`Obj` surface) outside of comments and string literals.

`Obj.magic : 'a -> 'b` is OCaml's universal type cast. It bypasses
the type system entirely. There are a small number of legitimate
uses (heterogeneous containers, GADT-less existentials, FFI shims
with proven memory-layout invariants) but in LLM-generated OCaml it
almost always shows up because the model wanted to "make the types
line up" without thinking through the algebra. The cost: undefined
behavior, segfaults, silent corruption, and sometimes a runtime that
keeps going long enough to corrupt persistent state before crashing.

## When to use

- Reviewing LLM-generated OCaml snippets before merging.
- CI lint over `*.ml` / `*.mli` files in a sample/example directory.
- Pre-commit lint on agent-authored OCaml.

## How to run

```
python3 detect.py <file_or_dir> [<file_or_dir> ...]
```

Exit code is `1` if any findings, `0` otherwise. Findings print as
`path:line:col: <kind> \u2014 <snippet>`.

## What it flags

- `obj-magic`
- `obj-repr`
- `obj-obj`
- `obj-field`
- `obj-set_field`
- `obj-unsafe_set_field`
- `obj-unsafe_get`

… anywhere outside an OCaml `(* ... *)` block comment (nested
comments are handled) or a `"..."` string literal.

## What it intentionally skips

- `open Obj` / `module M = Obj` — these reference the module without
  invoking an unsafe primitive.
- Mentions inside `(* ... *)` comments (including nested ones) or
  `"..."` strings.

## Known false-positive sources

- A user-defined `Obj` module that re-exports symbols named `magic`,
  `repr`, etc. would produce findings. This is intentionally rare in
  real codebases, and reviewers who hit it should rename the symbol
  rather than weaken the detector.

## Files

- `detect.py` — the detector (python3 stdlib only, single-pass scan).
- `bad/` — five OCaml files that MUST trigger.
- `good/` — three OCaml files that MUST NOT trigger.
- `smoke.sh` — runs the detector and asserts bad-hits > 0, good-hits == 0.

## Example output

```
$ python3 detect.py bad/
bad/01_force_cast.ml:3:3: obj-magic \u2014 Obj.magic s
bad/02_heterogeneous_list.ml:4:32: obj-magic \u2014 let unwrap_int (Any x) : int = Obj.magic x
bad/03_repr_round_trip.ml:3:11: obj-repr \u2014 let r = Obj.repr x in
bad/03_repr_round_trip.ml:4:3: obj-obj \u2014 Obj.obj r
bad/04_field_poke.ml:3:11: obj-repr \u2014 let r = Obj.repr x in
bad/04_field_poke.ml:4:3: obj-field \u2014 Obj.field r 0
bad/04_field_poke.ml:7:11: obj-repr \u2014 let r = Obj.repr x in
bad/04_field_poke.ml:8:3: obj-set_field \u2014 Obj.set_field r 0 (Obj.repr v)
bad/04_field_poke.ml:8:24: obj-repr \u2014 Obj.set_field r 0 (Obj.repr v)
bad/05_unsafe_array.ml:3:3: obj-magic \u2014 Obj.magic (Obj.unsafe_get (Obj.repr a) i)
bad/05_unsafe_array.ml:3:14: obj-unsafe_get \u2014 Obj.magic (Obj.unsafe_get (Obj.repr a) i)
bad/05_unsafe_array.ml:3:30: obj-repr \u2014 Obj.magic (Obj.unsafe_get (Obj.repr a) i)
# 12 finding(s)
```
