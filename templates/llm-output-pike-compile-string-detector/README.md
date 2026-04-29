# llm-output-pike-compile-string-detector

Single-pass python3 stdlib scanner that flags runtime-compile sinks
in [Pike](https://pike.lysator.liu.se/) source files emitted by LLMs.

## What it detects

Pike ships its compiler at runtime. Any of the following turn a
string into executable Pike code:

| Function                                    | What it does                          |
| ------------------------------------------- | ------------------------------------- |
| `compile_string(src [, fname [, handler]])` | parse + compile `src` → `program`     |
| `compile_file(path)`                        | read `path`, then `compile_string` it |
| `compile(src)`                              | low-level compile of a CPP-expanded blob |
| `cpp(src [, fname])`                        | C-pre-process `src` (typically piped into `compile`) |

Once any of these returns a `program`, the typical next step is
`prog()` to instantiate it — at which point the source executes.
A non-literal first argument is the Pike flavour of
`eval(user_input)`.

| Pattern                                  | Kind                          |
| ---------------------------------------- | ----------------------------- |
| `compile_string(<arg>, ...)` arg dynamic | `pike-compile-string-dynamic` |
| `compile_string(<arg>, ...)` arg literal | `pike-compile-string`         |
| `compile_file(<arg>)` arg dynamic        | `pike-compile-file-dynamic`   |
| `compile_file(<arg>)` arg literal        | `pike-compile-file`           |
| `compile(<arg>)`                         | `pike-compile`                |
| `cpp(<arg>, ...)` arg dynamic            | `pike-cpp-dynamic`            |

The first-arg classification for `compile_string` is deliberate:
the optional `filename` and `handler` arguments can legitimately
be variables; only the *source* arg matters for the smell.

## False-positive notes

* `//` and `/* ... */` comments are blanked before matching, so
  doc-comments mentioning `compile_string("evil " + x)` do not trip.
* Double-quoted string contents are blanked. `#"..."` Pike pre-quoted
  strings work too — the leading `#` is left in place; the body is
  blanked the same way as a regular string.
* Module-prefixed forms (`predef::compile_string(...)`,
  `master()->compile_string(...)`) are matched because we anchor on
  the bareword token, not on a leading line position.
* `cpp("literal")` is intentionally *not* flagged — using `cpp` on a
  fixed string is a documentation curiosity, not a security smell.
* The detector does not attempt to prove a variable is sanitized.

Suppression: append `// pike-eval-ok` on the line.

## Usage

```
python3 detector.py <file_or_dir> [<file_or_dir> ...]
```

Recurses into directories looking for `*.pike`, `*.pmod`, `*.pmod.in`,
and `*.pike.in`. Exit code is `1` if any findings were emitted, `0`
otherwise. python3 stdlib only — no external deps.

## Worked example

The `examples/` tree contains five intentionally-bad files (covering
each sink kind, including the `predef::` prefix and the
`cpp` → `compile` chain) and three clean ones.

```
$ python3 detector.py examples/bad
examples/bad/01_compile_string_stdin.pike:4:17: pike-compile-string-dynamic — program p = compile_string(src);
examples/bad/02_compile_file_argv.pike:3:17: pike-compile-file-dynamic — program p = compile_file(argv[1]);
examples/bad/03_compile_string_concat.pike:5:17: pike-compile-string-dynamic — program p = compile_string(src, "user.pike");
examples/bad/04_cpp_then_compile.pike:4:23: pike-cpp-dynamic — string expanded = cpp(blob, "snippet.h");
examples/bad/04_cpp_then_compile.pike:5:17: pike-compile — program p = compile(expanded);
examples/bad/05_predef_compile_string.pike:4:25: pike-compile-string-dynamic — program p = predef::compile_string(src);
# 6 finding(s)
$ echo $?
1

$ python3 detector.py examples/good
# 0 finding(s)
$ echo $?
0
```

5 / 5 bad files flagged (the `cpp_then_compile` file legitimately
emits two findings — one for `cpp(blob, ...)`, one for the
subsequent `compile(expanded)`), 0 / 3 good files flagged. Exit
codes match the contract. The `good/03_suppressed.pike` file
contains a `compile_string(trusted, "trusted.pike")` call carrying
`// pike-eval-ok` and is correctly silenced.

## Why this template exists

Pike's runtime compiler is the language's superpower — and exactly
why LLM-generated Pike snippets gravitate toward `compile_string`
when they want to "just run that string". In any service that
ingests Pike from outside (a Roxen module template, a notebook
kernel, a config DSL), every `compile_string` whose first argument
is not a literal is a remote-code-execution surface. This detector
provides a deterministic, dependency-free CI check: did this
LLM-produced Pike file gain a new compile sink?
