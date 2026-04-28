# llm-output-c-strcpy-unbounded-detector

Flags calls to unbounded C string functions (`strcpy`, `strcat`,
`sprintf`, `vsprintf`, `gets`) in `.c` / `.h` source.

## The smell

```c
void greet(const char *name) {
    char buf[16];
    strcpy(buf, name);   // <-- name length never checked
}
```

`strcpy`, `strcat`, `sprintf`, and friends accept no destination size.
If the source is attacker-influenced (or just longer than the developer
assumed), the write runs off the end of the buffer. This is the textbook
stack/heap overflow primitive that has produced thousands of CVEs.

`gets` is even worse — it has no length argument **at all** and was
removed from the C language in C11 — yet LLMs still emit it.

## Why LLMs produce it

These four function names are the most-cited string functions in
training data: K&R, decades of beginner tutorials, Stack Overflow
answers from 2008, embedded C samples. The bounded equivalents
(`strncpy`, `strlcpy`, `strncat`, `strlcat`, `snprintf`, `fgets`) appear
much less frequently and require a size argument the model has to
invent. Under uncertainty the model defaults to the shorter, more
familiar shape — even when the surrounding code already has the
required size in scope.

## How the detector works

Single-pass per-line scanner over `.c` / `.h` files:

1. **Mask comments and string/char literals.** Block comments
   (`/* ... */`), line comments (`// ...`), string literals (`"..."`),
   and char literals (`'.'`) are replaced with spaces so banned names
   that appear inside docs/strings don't trigger.
2. **Scan for each banned identifier as a whole word.** Word boundaries
   are checked on the left so that `mystrcpy`, `strcpy_safe`,
   `do_strcat_with_check`, etc. are *not* flagged.
3. **Require an immediately-following `(`** (skipping whitespace) so
   that the match is a call/prototype shape, not a bare identifier.

Stdlib only.

## False-positive caveats

- **Prototypes / extern declarations.** A line like
  `extern char *strcpy(char *, const char *);` matches the call shape
  and *will* be flagged. This is intentional: such redeclarations are
  rare in real code, and when they appear they usually indicate the
  author is wrapping the banned function — worth a human glance.
- **Macro definitions.** `#define LOG(x) sprintf(buf, "%s", x)` will
  flag at the macro definition line. That is correct — the macro
  body itself contains the unsafe call.
- **Function pointer declarations** that don't have an immediate `(`
  after the name (`copy_fn p;`) do not match. Indirect calls through
  a pointer named differently are not detected — the scanner is
  syntactic, not semantic.
- The detector does not know whether `dst` has been pre-sized to
  exactly `strlen(src) + 1` and the call is therefore safe. Such cases
  are a tiny minority and still worth flagging for review.

## Usage

```
python3 detector.py path/to/c/project
```

Exit code `0` if no hits, `1` if any.

## Smoke test

See `SMOKE.md`. Current counts: `bad/` = 10 hits across 6 files,
`good/` = 0 hits across 6 files.
