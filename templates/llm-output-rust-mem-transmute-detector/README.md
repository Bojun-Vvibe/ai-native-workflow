# llm-output-rust-mem-transmute-detector

Detect calls to `std::mem::transmute` (and the bare `transmute` after a
`use`) in LLM-generated Rust code.

## Why

`std::mem::transmute<T, U>` reinterprets the bits of a `T` as a `U`
without any conversion. It is one of the most dangerous primitives in
the Rust standard library: any mismatch in size, alignment, validity
invariants, or aliasing rules is **immediate undefined behavior**.

LLMs reach for `transmute` reflexively when they:

- want to "cast" between integer and float types
  (correct tool: `f64::from_bits` / `to_bits` or `as`);
- want to convert `&[u8]` to `&str` (correct tool:
  `std::str::from_utf8`);
- want to change a slice's element type (correct tool:
  `bytemuck::cast_slice` or a manual length-and-alignment check);
- want to convert between function pointer types or attach a lifetime
  (almost always wrong in safe-looking code).

Almost every call site has a safer, total replacement. CWE-704
(Incorrect Type Conversion or Cast).

## What this flags

A finding is emitted whenever a call to one of:

- `std::mem::transmute(...)`
- `mem::transmute(...)`
- `transmute(...)` (bare, requires a prior `use` — we don't try to
  prove the `use` is present, since the LLM may have forgotten it)
- `std::mem::transmute_copy(...)` / `mem::transmute_copy(...)` /
  `transmute_copy(...)` (same hazard, sometimes worse since it can
  read past the source's allocation)

is found anywhere the call is *callable*: either inside an
`unsafe { ... }` block, or inside an `unsafe fn`. Calls outside an
`unsafe` context are rejected by the compiler, so we don't bother
flagging them — but we still report them as a quality issue, because
LLMs sometimes emit non-compiling `transmute(x)` snippets.

A per-line suppression marker is supported:

    // llm-allow:mem-transmute

## What this does NOT flag

- `mem::size_of`, `mem::align_of`, `mem::swap`, `mem::replace`,
  `mem::take`, `mem::forget`, `mem::drop` — these are safe and fine.
- `std::mem::transmute` mentioned only in a doc comment or string
  literal — Rust-aware tokenization blanks comments and strings.
- A call site marked with the suppression marker on the same line or
  the line immediately above.

## False-positive notes

`transmute_copy` is sometimes load-bearing in FFI shims that need to
copy out of a `repr(C)` union without consuming it. If you have such
a call site reviewed and accepted, mark it with
`// llm-allow:mem-transmute`. Per the project's review-everything
posture, this should be rare.

## Usage

    python3 detect.py <file_or_dir> [...]

Exit code is `1` if any findings, `0` otherwise. Stdlib only.
Recognized extensions: `.rs`, `.md`, `.markdown` (Rust fences in
Markdown are extracted and scanned).

## Verify

    bash verify.sh

Expected output: `bad findings: 7 (rc=1)`, `good findings: 0 (rc=0)`,
`PASS`.
