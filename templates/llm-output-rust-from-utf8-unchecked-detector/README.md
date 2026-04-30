# llm-output-rust-from-utf8-unchecked-detector

Static detector for the Rust anti-pattern of calling
`std::str::from_utf8_unchecked` (or `String::from_utf8_unchecked`)
on bytes the surrounding code has not validated as UTF-8.

The safety contract on these constructors is:

> The bytes passed in must be valid UTF-8.

If they are not, the resulting `&str` / `String` causes **immediate
undefined behavior**, not a panic and not a `Result::Err`. LLM-
generated Rust code very commonly reaches for the unchecked variant
"to avoid the `Result`" without any prior validation.

```rust
// dangerous — bytes from the network are not validated
let s: &str = unsafe { std::str::from_utf8_unchecked(payload) };

// safer — Result-returning constructor
let s: &str = std::str::from_utf8(payload)?;
```

## What this flags

A finding is emitted whenever
`std::str::from_utf8_unchecked(...)`,
`String::from_utf8_unchecked(...)`,
or a bare `from_utf8_unchecked(...)` (after `use`) is called and **all**
of the following hold:

* the call is lexically inside an `unsafe { ... }` block (the only
  way a real call site is reachable);
* the surrounding function scope does **not** contain a preceding
  validation hint. Any of the following counts as evidence:
  - `std::str::from_utf8` / `str::from_utf8`,
  - `String::from_utf8`,
  - `simdutf8::basic::from_utf8` / `simdutf8::compat::from_utf8`,
  - `.is_ascii()`,
  - `.utf8_chunks()`,
  - an `assert!` / `debug_assert!` whose message mentions
    `from_utf8`, `is_ascii`, or `utf8_chunks`.

The "function scope" is approximated by walking backward from the
`unsafe` keyword to the nearest unmatched `{` (the enclosing
`fn`/`impl`/closure body).

Rust-aware token handling:

* `//` line comments and `/* ... */` block comments (with depth
  tracking — Rust block comments nest) are blanked.
* `"..."` and `r#"..."#` raw string literal bodies are blanked.

A finding is suppressed if the same line, or the line immediately
above, carries `// llm-allow:from-utf8-unchecked`.

The detector also extracts fenced `rust` (or `rs`, or unlabeled) code
blocks from Markdown.

## Safe alternatives

* `std::str::from_utf8(bytes)` returns `Result<&str, Utf8Error>` and
  is the right default. The validation loop is hand-vectorized and
  cheap.
* `String::from_utf8(vec)` returns `Result<String, FromUtf8Error>`,
  which lets the caller recover the original bytes.
* For very hot paths, validate once with `simdutf8::basic::from_utf8`
  (SIMD-accelerated) and only then construct via the unchecked
  variant — the detector accepts the simdutf8 call as evidence.
* Never feed network/file/FFI buffers directly into an unchecked
  constructor.

## CWE references

* **CWE-119**: Improper Restriction of Operations within the Bounds
  of a Memory Buffer.
* **CWE-704**: Incorrect Type Conversion or Cast.
* **CWE-758**: Reliance on Undefined, Unspecified, or Implementation-
  Defined Behavior.

## Usage

```
python3 detect.py <file_or_dir> [...]
```

Exit code `1` on any findings, `0` otherwise. python3 stdlib only.

## Worked example

```
$ bash verify.sh
bad findings:  6 (rc=1)
good findings: 0 (rc=0)
PASS
```

See `examples/bad/` and `examples/good/` for the concrete fixtures.
