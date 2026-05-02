# llm-output-rust-unsafe-block-without-safety-comment-detector

Static lint that flags Rust `unsafe { ... }` blocks that are not
preceded (or trailed on the same line) by a `// SAFETY:`
justification comment.

Rust's `unsafe` keyword tells the compiler "trust me, I have manually
verified the invariants the safe surface couldn't prove". The
community-accepted convention — codified in the Rust API guidelines,
the `clippy::undocumented_unsafe_blocks` lint, and the `std` library
style guide — is that **every** `unsafe { ... }` block must be
immediately preceded by a comment of the form
`// SAFETY: <why this is sound>`.

LLMs writing Rust frequently emit `unsafe { ... }` blocks that bypass
borrow-check / type-safety / pointer-validity guarantees without any
soundness justification. This detector flags those cases so a human
can decide whether the unsafety is actually warranted (and, if so,
document it).

## What it catches

- Any `unsafe` keyword followed (after optional whitespace) by `{` —
  i.e. an unsafe BLOCK.
- Declarations (`unsafe fn`, `unsafe trait`, `unsafe impl`,
  `unsafe extern "C" { ... }`) are intentionally NOT flagged: the
  convention applies to *callers* of unsafe.
- A `// SAFETY:` comment on the same line as the `unsafe` block, or
  on any of the contiguous comment lines immediately preceding it
  (with `#[...]` attributes allowed in between), satisfies the
  check.
- A simple string- and comment-aware tokenizer pass strips `"..."`,
  `r#"..."#`, `// ...`, and `/* ... */` so the keyword inside a
  string literal or doc comment doesn't trip the detector.

## CWE references

(When the unsafety is actually a bug — these guide reviewer attention,
they are not all triggered automatically.)

- [CWE-119](https://cwe.mitre.org/data/definitions/119.html):
  Improper Restriction of Operations within the Bounds of a Memory
  Buffer
- [CWE-416](https://cwe.mitre.org/data/definitions/416.html):
  Use After Free
- [CWE-787](https://cwe.mitre.org/data/definitions/787.html):
  Out-of-bounds Write
- [CWE-1265](https://cwe.mitre.org/data/definitions/1265.html):
  Unintended Reentrant Invocation of Non-reentrant Code

## False-positive surface

- Generated code (e.g. `bindgen` output) — suppress per file with the
  comment string `rust-unsafe-audit-skip` anywhere in the file.
- Macro-generated unsafe blocks (e.g. `some_macro! { unsafe { ... } }`)
  — the macro authors should document at the macro call site; this
  detector does still flag the expansion site if it ends up in the
  source tree.
- `unsafe fn` / `unsafe trait` / `unsafe impl` declarations are
  intentionally NOT flagged.
- A SAFETY comment that is itself misleading or wrong — the detector
  only checks for *presence*, not *correctness*; reviewers must
  still read the justification.

## Worked example

Live run:

```sh
$ ./verify.sh
bad=3/3 good=0/4
PASS
```

Per-bad-file output:

```
$ python3 detector.py examples/bad/01_no_comment.rs
examples/bad/01_no_comment.rs:4:unsafe { ... } block missing `// SAFETY:` justification comment on the preceding line

$ python3 detector.py examples/bad/02_only_generic_comment.rs
examples/bad/02_only_generic_comment.rs:5:unsafe { ... } block missing `// SAFETY:` justification comment on the preceding line

$ python3 detector.py examples/bad/03_two_blocks_no_safety.rs
examples/bad/03_two_blocks_no_safety.rs:9:unsafe { ... } block missing `// SAFETY:` justification comment on the preceding line
examples/bad/03_two_blocks_no_safety.rs:13:unsafe { ... } block missing `// SAFETY:` justification comment on the preceding line
```

## Files

- `detector.py` — scanner. Exit code = number of files with at least
  one finding.
- `verify.sh` — runs all `examples/bad/` and `examples/good/` and
  reports `bad=X/X good=0/Y` plus `PASS` / `FAIL`.
- `examples/bad/` — expected to flag (3 files: no comment at all,
  generic comment that lacks `SAFETY:`, two unsafe blocks neither
  documented).
- `examples/good/` — expected to pass clean (4 files: multi-line
  `// SAFETY:` block, trailing same-line `// SAFETY:` plus an
  attribute between SAFETY and unsafe, declarations + string-literal
  containing the keyword, suppression marker).
