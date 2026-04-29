# llm-output-fsharp-reflection-invoke-detector

## Purpose

Detect F# (and surrounding .NET) code that reaches into runtime
reflection to dispatch methods, properties, fields, types, or
assemblies by **string name** at runtime.

The flagged shapes:

| Kind | Example |
| --- | --- |
| `get-method` | `t.GetMethod("Foo")` |
| `get-property` | `t.GetProperty("Foo")` |
| `get-field` | `t.GetField("Foo")` |
| `invoke-member` | `t.InvokeMember("Foo", ...)` |
| `method-invoke` | `mi.Invoke(target, args)` (preceded by a `MethodInfo`-shaped name) |
| `dynamic-invoke` | `d.DynamicInvoke(args)` |
| `activator-create` | `Activator.CreateInstance(t, args)` |
| `type-get-type` | `Type.GetType("Some.Name")` |
| `assembly-load` | `Assembly.Load(...)` / `Assembly.LoadFrom(...)` / `Assembly.LoadFile(...)` |

## Why this matters for LLM-emitted F#

F# already has powerful, type-safe ways to express dynamic dispatch:
discriminated unions, interfaces, and active patterns. LLMs that have
seen a lot of C# tutorials reach for `GetMethod(name) + Invoke(...)`
to "call a method by name", which:

1. throws away all type safety,
2. opens the dispatch table to whatever string the caller supplies,
3. is almost always combined with `Activator.CreateInstance` and
   `Type.GetType("…")`, which together are sufficient to construct
   arbitrary types and execute arbitrary methods if the input string
   is attacker-influenced — i.e. RCE inside the .NET process.

## When to use

- Reviewing LLM-generated `*.fs` / `*.fsx` / `*.fsi` snippets before merging.
- CI lint over agent-authored F# in a sample directory.
- Spot-checking a port of C# code into F# where the model preserved
  reflection patterns instead of rewriting them.

## How to run

```
python3 detect.py <file_or_dir> [<file_or_dir> ...]
```

Exit code is `1` if any findings, `0` otherwise. Findings print as
`path:line:col: <kind> — <snippet>`.

## What it skips

- `// ...` line comments.
- `(* ... *)` block comments (single- and multi-line).
- `"..."`, `@"..."`, and `"""..."""` string literals.
- Plain `.Invoke(` that is NOT preceded by a likely-reflection token
  (avoids false positives on event handlers and `Option.Invoke`-style
  domain code).
- `Activator.CreateInstance<T>()` generic form is also matched (the
  `<T>` does not interrupt the `(`).

## Heuristic limits

This is a line-based heuristic. It will miss reflection that has been
split across multiple lines using F# pipelines in unusual shapes, and
it will conservatively skip bare `.Invoke(` calls on values whose
names do not match the `MethodInfo`-family heuristic. The goal is to
surface the easy-mode RCE shapes that LLMs emit by reflex.

## Files

- `detect.py` — the detector (python3 stdlib only).
- `bad/` — four F# files that MUST trigger.
- `good/` — two F# files that MUST NOT trigger.
- `smoke.sh` — runs the detector and asserts bad-hits > 0, good-hits == 0.

## Smoke test (real output)

```
$ ./smoke.sh
bad_hits=10
good_hits=0
OK: bad=10 good=0

$ python3 detect.py bad/
bad/01_get_method_invoke.fs:7:15: get-method — let mi = t.GetMethod(name)
bad/01_get_method_invoke.fs:8:5: method-invoke — mi.Invoke(target, args)
bad/02_assembly_load.fs:7:15: assembly-load — let asm = Assembly.LoadFrom(asmPath)
bad/02_assembly_load.fs:9:16: activator-create — let inst = Activator.CreateInstance(t)
bad/02_assembly_load.fs:10:6: invoke-member — t.InvokeMember(methodName, BindingFlags.InvokeMethod, null, inst, [||])
bad/03_type_get_type.fs:7:13: type-get-type — let t = Type.GetType(typeFullName)
bad/03_type_get_type.fs:8:5: activator-create — Activator.CreateInstance(t, args)
bad/03_type_get_type.fs:11:29: get-property — let p = target.GetType().GetProperty(propName)
bad/04_dynamic_invoke.fsx:7:6: dynamic-invoke — d.DynamicInvoke(args)
bad/04_dynamic_invoke.fsx:10:29: get-field — let f = target.GetType().GetField(fieldName)
# 10 finding(s)

$ python3 detect.py good/
# 0 finding(s)
```
