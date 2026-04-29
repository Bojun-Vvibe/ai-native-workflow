# llm-output-squirrel-compilestring-detector

Single-pass detector for **Squirrel `compilestring(...)`** runtime
code-evaluation sinks.

## Why this exists

Squirrel is a small embeddable scripting language used in games
(notably Left 4 Dead 2's vscripts) and embedded systems. Its
standard library exposes:

```squirrel
compilestring(src [, bindname])
```

which compiles a Squirrel source string at runtime and returns a
closure that, when called, executes that code in the host VM with
full access to the root table. A compiled-then-called closure is
the canonical eval-equivalent in Squirrel.

Whenever the source argument is anything other than an audited
literal, the program is loading code chosen at runtime from data
that may be attacker-controllable: a config file, a network
response, a chat command, an entity keyvalue. Because the produced
closure runs with the full host environment, this is equivalent to
a Lua `loadstring(...)()`.

LLM-emitted Squirrel code reaches for `compilestring` whenever the
model wants a "tiny scripting hook" or "user-supplied formula" and
does not know the safer patterns (a small interpreter over a fixed
grammar, a data-only config table, or sandboxing via a fresh root
table with `setroottable`).

## What it flags

| Construct                  | Why                                  |
| -------------------------- | ------------------------------------ |
| `compilestring(...)`       | Primary eval sink                    |
| `::compilestring(...)`     | Explicit root-table-scoped variant   |

The match anchors on optional `::`, the symbol `compilestring`
(not preceded by an identifier character), and an opening `(`.
Identifiers that merely contain `compilestring`
(`my_compilestring_helper`, `compilestringify`) do not match.

## What it ignores

- Mentions inside `//` line comments.
- Mentions inside `#` line comments (Squirrel accepts both).
- Mentions inside `/* ... */` block comments.
- Mentions inside `"..."` strings, `'...'` character literals, and
  `@"..."` verbatim strings (verbatim treats `""` as an escaped
  quote).
- Identifiers that merely contain the substring (see above).
- Lines marked with the suppression comment `// eval-ok` or
  `# eval-ok`.

## Usage

```sh
python3 detect.py <file_or_dir> [<file_or_dir> ...]
```

Exit code `1` on any finding, `0` otherwise. Python 3 stdlib only,
no third-party dependencies. Recurses into directories looking for
`*.nut`.

## Verified output

```
$ python3 detect.py examples/bad/
examples/bad/01_basic.nut:3:12: squirrel-compilestring — local fn = compilestring(src);
examples/bad/02_root_scoped.nut:3:12: squirrel-root-compilestring — return ::compilestring(src);
examples/bad/03_compile_call.nut:2:16: squirrel-compilestring — local result = compilestring("return 1+2")();
examples/bad/04_class_method.nut:4:25: squirrel-compilestring — local closure = compilestring(cfg.script);
examples/bad/05_concat.nut:4:12: squirrel-compilestring — return compilestring(body)();
examples/bad/06_loop.nut:3:15: squirrel-compilestring — local f = compilestring(src);
# 6 finding(s)

$ python3 detect.py examples/good/
# 0 finding(s)
```

The `examples/good/` files correctly produce zero findings,
including the doc strings that mention `compilestring(...)` inside
literals and verbatim strings, the lookalike identifiers like
`my_compilestring_helper` and `compilestringify`, the comment
mentions, and the suppressed `// eval-ok` line.

## Layout

```
detect.py                    # the scanner
examples/bad/*.nut           # six intentional violations
examples/good/*.nut          # four files with zero violations
```
