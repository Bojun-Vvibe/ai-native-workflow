# llm-output-chuck-machine-add-detector

Single-pass detector for **ChucK `Machine.add` / `Machine.replace` /
`Machine.spork` / `Machine.eval`** runtime code-load sinks.

## Why this exists

ChucK's `Machine` interface lets a running VM load and execute another
ChucK source file (or string) at runtime. Whenever the argument is
not a manifest, audited string literal, the program is loading code
chosen from data that may be attacker-controllable (config, network,
user prompt, OSC message).

LLM-generated ChucK glue code frequently reaches for `Machine.add`
when it wants dynamic patch loading without knowing the safer
patterns (a static dispatch table, or path allow-listing).

## What it flags

| Construct                       | Why                                       |
| ------------------------------- | ----------------------------------------- |
| `Machine.add("patches/x.ck")`   | Code-load even with a literal path        |
| `Machine.add(name + ".ck")`     | True dynamic load -- attacker-influenced  |
| `Machine.replace(id, expr)`     | Hot-swap of a running shred               |
| `Machine.spork(expr)`           | Fork + load                               |
| `Machine.eval(code)`            | Direct string evaluation                  |

## What it ignores

- Mentions of `Machine.add(` inside `// line` or `/* block */`
  comments.
- The substring inside `"..."` string literals (e.g. doc strings).
- Other `Machine.*` methods that don't load code (`Machine.crash`,
  `Machine.realtime`, `Machine.intsize`, etc.).
- Lines marked with the suppression comment `// machine-add-ok`.

## Usage

```sh
python3 detect.py <file_or_dir> [<file_or_dir> ...]
```

Exit code `1` on any finding, `0` otherwise. Python 3 stdlib only,
no third-party dependencies. Recurses into directories looking for
`*.ck`.

## Verified output

```
$ python3 detect.py examples/
examples/bad/01_basic_add.ck:3:1: chuck-machine-add — Machine.add("patches/lead.ck");
examples/bad/02_dynamic_add.ck:3:5: chuck-machine-add — Machine.add("patches/" + name + ".ck");
examples/bad/03_replace.ck:4:5: chuck-machine-replace — Machine.replace(currentID, nextFile);
examples/bad/04_spork_dynamic.ck:3:1: chuck-machine-spork — Machine.spork(voicePath);
examples/bad/05_eval_string.ck:3:1: chuck-machine-eval — Machine.eval(code);
examples/bad/06_inline_call.ck:2:26: chuck-machine-add — if (me.arg(0) == "boot") Machine.add("startup.ck");
# 6 finding(s)
```

The `examples/good/` files correctly produce zero findings, including
the suppressed `// machine-add-ok` line and the API-doc string that
mentions `Machine.add(` inside a string literal.

## Layout

```
detect.py                # the scanner
examples/bad/*.ck        # six intentional violations
examples/good/*.ck       # four files with zero violations
```
