# llm-output-dart-mirrors-detector

Single-pass python3 stdlib scanner that flags risky uses of
`dart:mirrors` reflective dispatch in Dart code emitted by LLMs.

## What it detects

`dart:mirrors` exposes runtime reflection. Its `invoke`,
`invokeGetter`, `invokeSetter`, and `newInstance` methods take a
`Symbol` and an argument list and dispatch to whatever method or
constructor that symbol names. When the symbol comes from
LLM-generated text, network input, a config file, or anywhere else
under attacker influence, this is a code-execution sink: the caller
hands the attacker the choice of which method to run.

The detector flags:

| Pattern | Kind | Why |
| --- | --- | --- |
| `import 'dart:mirrors'` | `dart-mirrors-import` | Unsupported in AOT; commonly the *only* signal that a file is doing reflective dispatch. |
| `<expr>.invoke(...)` after `reflect(...)` in the same file | `dart-mirrors-invoke` | Dynamic method call on a `Mirror`. |
| `<expr>.invokeGetter(...)` | `dart-mirrors-invokeGetter` | Dynamic getter read. |
| `<expr>.invokeSetter(...)` | `dart-mirrors-invokeSetter` | Dynamic setter write. |
| `<expr>.newInstance(...)` | `dart-mirrors-newInstance` | Dynamic constructor invocation. |
| `Function.apply(...)` | `dart-function-apply` | Top-level reflective call form. |

The recommended fix is an explicit allow-list (`switch` on a known
set of names) without mirrors at all. That also lets the program
tree-shake under AOT, where `dart:mirrors` is unavailable.

## False-positive notes

* String literals and `// ...` comments are blanked out before
  matching, so docs that mention `.invoke(` or `import 'dart:mirrors'`
  do not trip.
* `.invoke(` / `.newInstance(` only fire if the file *also* mentions
  a reflective entry-point (`reflect(`, `reflectClass(`, `reflectType(`,
  `currentMirrorSystem(`). A user-defined `class Foo { void invoke()
  {} }` in a non-mirror file is not flagged.
* `.apply(` alone is **not** flagged; only `Function.apply(` (the
  reflective top-level form) and `.apply(` inside a file that already
  imported mirrors.
* Triple-quoted multi-line strings are out of scope for this
  single-pass scanner — flag with `// mirrors-ok` if needed.

Suppression: append `// mirrors-ok` on the same line.

## Usage

```
python3 detector.py <file_or_dir> [<file_or_dir> ...]
```

Recurses into directories looking for `*.dart`. Exit code `1` if any
findings, `0` otherwise. python3 stdlib only.

## Worked example

```
$ python3 detector.py examples/bad examples/good
examples/bad/01_invoke_user_symbol.dart:2:1: dart-mirrors-import — import 'dart:mirrors';
examples/bad/01_invoke_user_symbol.dart:11:4: dart-mirrors-invoke — m.invoke(Symbol(userMethod), args);
examples/bad/02_invoke_getter.dart:1:1: dart-mirrors-import — import 'dart:mirrors';
examples/bad/02_invoke_getter.dart:5:11: dart-mirrors-invokeGetter — return m.invokeGetter(Symbol(attr));
examples/bad/03_new_instance.dart:1:1: dart-mirrors-import — import 'dart:mirrors';
examples/bad/03_new_instance.dart:6:12: dart-mirrors-newInstance — return cm.newInstance(Symbol(''), positional).reflectee;
examples/bad/04_invoke_setter.dart:1:1: dart-mirrors-import — import 'dart:mirrors';
examples/bad/04_invoke_setter.dart:4:13: dart-mirrors-invokeSetter — reflect(o).invokeSetter(Symbol(name), value);
examples/bad/05_function_apply.dart:3:10: dart-function-apply — return Function.apply(fn, positional, named);
# 9 finding(s)
```

5 bad files produce 9 findings; 3 good files produce 0.
