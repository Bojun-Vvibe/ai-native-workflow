# llm-output-haxe-reflect-callmethod-detector

Single-pass detector for **Haxe `Reflect.callMethod`,
`Reflect.field`, `Reflect.setField`, and the `Type.createInstance`
family** — the runtime dynamic-dispatch escape hatches that defeat
Haxe's type checker.

## Why this exists

Haxe is statically typed, but its `Reflect` and `Type` modules let
you turn a string into a method call or a class instantiation. When
the name comes from data (config, RPC frame, query string,
deserialized JSON), the program is dispatching to whatever the
caller wants.

LLM-generated Haxe code reaches for `Reflect.callMethod` and
`Type.createInstance` whenever the model wants "a tiny RPC layer"
or "let the caller pick which handler to run" without knowing the
safer patterns (a closed `Map<String, Method>` dispatch table, or
a sealed enum + switch).

## What it flags

| Construct                            | Why                                       |
| ------------------------------------ | ----------------------------------------- |
| `Reflect.callMethod(...)`            | Primary dynamic-call sink                 |
| `Reflect.field(o, x)`                | Front half of the dispatch pipeline       |
| `Reflect.setField(o, x, v)`          | Mirror write sink                         |
| `Type.createInstance(c, args)`       | Dynamic constructor                       |
| `Type.createEmptyInstance(c)`        | Bypasses constructor entirely             |
| `Type.resolveClass(name)`            | String-to-Class lookup, ctor precursor    |

## What it ignores

- Mentions inside `// line` and `/* block */` comments.
- Mentions inside `"..."` and `'...'` string literals.
- Lookalike identifiers like a user-defined `MyReflect.callMethod`
  or a `TypeRegistry.createInstance` — the regex anchors on the
  exact `Reflect.` and `Type.` prefixes.
- Lines marked with the suppression comment `// reflect-ok`.

## Usage

```sh
python3 detect.py <file_or_dir> [<file_or_dir> ...]
```

Exit code `1` on any finding, `0` otherwise. Python 3 stdlib only,
no third-party dependencies. Recurses into directories looking for
`*.hx`.

## Verified output

```
$ python3 detect.py examples/bad/*
examples/bad/01_dispatch.hx:4:17: haxe-reflect-field — var m = Reflect.field(target, name);
examples/bad/01_dispatch.hx:5:16: haxe-reflect-callmethod — return Reflect.callMethod(target, m, args);
examples/bad/02_setfield.hx:4:9: haxe-reflect-setfield — Reflect.setField(target, name, value);
examples/bad/03_create_instance.hx:4:16: haxe-type-createinstance — return Type.createInstance(cls, args);
examples/bad/04_resolve_empty.hx:4:17: haxe-type-resolveclass — var c = Type.resolveClass(name);
examples/bad/04_resolve_empty.hx:5:16: haxe-type-createemptyinstance — return Type.createEmptyInstance(c);
examples/bad/05_literal_field.hx:5:16: haxe-reflect-field — return Reflect.field(o, "name");
examples/bad/06_hooks.hx:5:13: haxe-reflect-callmethod — Reflect.callMethod(target, Reflect.field(target, hookName), []);
examples/bad/06_hooks.hx:5:40: haxe-reflect-field — Reflect.callMethod(target, Reflect.field(target, hookName), []);
# 9 finding(s)

$ python3 detect.py examples/good/*
# 0 finding(s)
```

The `examples/good/` files correctly produce zero findings, including
the doc string that mentions `Reflect.callMethod` inside a literal,
the comment block, the lookalike identifiers `MyReflect.callMethod`
and `TypeRegistry.createInstance`, and the suppressed `// reflect-ok`
line.

## Layout

```
detect.py                    # the scanner
examples/bad/*.hx            # six intentional violations (9 findings total)
examples/good/*.hx           # four files with zero violations
```
