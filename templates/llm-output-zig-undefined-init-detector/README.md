# llm-output-zig-undefined-init-detector

Detects Zig variable / constant declarations initialized with the
`undefined` sentinel where the type is a scalar, pointer, optional, or
error-union — cases where reading before write is almost certainly a
bug.

## The antipattern

In Zig, `var x: T = undefined;` does not zero-initialize `x`; it
declares that the bytes are genuinely uninitialized and that reading
them before a definite assignment is **illegal behavior**. In Debug
and ReleaseSafe builds the runtime fills the bytes with `0xaa` to
make misuse obvious; in ReleaseFast / ReleaseSmall the bytes are
whatever was on the stack, and reads are undefined behavior the
optimizer is free to assume away.

There is a legitimate use: large stack-allocated buffers (`var buf:
[4096]u8 = undefined;`) that are about to be filled by a single OS
call (`std.posix.read`, `std.fmt.bufPrint`, etc.). For those, the
write-before-read invariant is locally obvious.

The dangerous shape is **scalar-typed or pointer-typed
declarations** initialized to `undefined`:

```zig
var count: u32 = undefined;        // BAD: silent garbage
var ptr: *Thing = undefined;       // BAD: dangling on first read
var maybe: ?Foo = undefined;       // BAD: optional discriminant garbage
var err: Error!u32 = undefined;    // BAD: error-union tag garbage
```

These shapes are bugs whenever a control-flow path reaches a read
before the unconditional write the author was planning to add later.
LLMs habitually emit them to silence "must be initialized" compile
errors without noticing that not every code path writes the value.

## Why LLMs emit it

- The Zig compiler error for "use of possibly-uninitialized variable"
  is intimidating, and `= undefined` makes it disappear.
- Many tutorials show buffer-style examples (`var buf: [N]u8 =
  undefined;`) and LLMs over-generalize the pattern to scalar fields
  and pointers.
- In struct literals, `field = undefined` is a fast way to "satisfy
  the compiler" when the author has not yet wired the field.

## What this scanner flags

Any `var` or `const` declaration whose type annotation is one of the
following and whose initializer is `undefined`:

- a built-in scalar (`u8`..`u128`, `i8`..`i128`, `usize`, `isize`,
  `f16`, `f32`, `f64`, `f80`, `f128`, `bool`, `void`, `noreturn`,
  `c_int`, `c_uint`, `c_long`, `c_ulong`, `c_short`, `c_ushort`,
  `c_char`, `c_longlong`, `c_ulonglong`)
- a pointer type prefix `*` or `*const ` or `[*]` or `[*c]` or `?*`
- an optional prefix `?` (other than `?*` already covered)
- an error-union prefix containing `!` (e.g. `Error!u32`)

Array types (`[N]T`, `[_]T`) and explicit `@TypeOf(...)` /
user-defined struct names are deliberately NOT flagged: those are the
common legitimate uses (buffers and zero-cost struct prep).

Comments (`//` to EOL) and string / multiline-string / character
literals are masked so matches inside them do not fire.

## Usage

```bash
python3 detect.py path/to/src
```

Exit code is `1` if any findings, `0` otherwise. Output format is
`<file>:<line>:<col>: undefined-init-<kind> — <snippet>`.

To smoke-test the bundled examples:

```bash
./smoke.sh
```

It runs the scanner against `bad/` and `good/` and asserts that bad
has at least one hit and good has none.

## Suggested wiring

- Run in pre-commit on staged `.zig` files.
- Allow legitimate uses by either (a) using an array type for the
  declaration, or (b) adding a trailing comment `// noinit-ok:
  <reason>` and extending this scanner to honor it (left as a
  follow-up — the current version is intentionally simple).
