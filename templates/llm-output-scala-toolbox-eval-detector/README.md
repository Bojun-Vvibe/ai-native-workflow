# llm-output-scala-toolbox-eval-detector

Single-pass Python stdlib scanner that detects use of Scala's
[`scala.tools.reflect.ToolBox`](https://www.scala-lang.org/api/2.13.x/scala-reflect/scala/tools/reflect/ToolBox.html)
runtime compile-and-execute API. LLM-generated Scala code reaches for
this whenever asked to "let users write expressions" or "make rules
configurable" — a textbook RCE sink that boots an in-process Scala
compiler.

## What it flags

| Pattern | Why it's dangerous |
| --- | --- |
| `import scala.tools.reflect.ToolBox` | Capability acquisition — the entire dangerous API surface lives behind this import. |
| `<mirror>.mkToolBox(...)` | Constructs the in-process compiler. |
| `<tb>.eval(<tree>)` | Compiles and executes a tree. Full RCE if the tree derives from untrusted input. |
| `<tb>.compile(<tree>)` | Compiles a tree into a `() => Any` thunk; calling the thunk is the exec step. |
| `<tb>.parse(<string>)` | Parses a source string into a tree. Often immediately fed to `eval`/`compile`; flagging the parse catches the precursor. |

The `eval` / `compile` / `parse` matches are **gated**: they only fire
on a line that — together with the previous 4 lines — contains a
context token (`ToolBox`, `toolbox`, `tb`, `mirror`, `currentMirror`,
`cm`, `reflect.runtime`, `scala.tools.reflect`). This filters out
`Future.eval`, `Regex.compile`, `LocalDate.parse`, JSON parsers, etc.
that share method names with the Toolbox API.

## How it works

1. Read each `.scala` / `.sc` file.
2. **Mask** lexical regions so they cannot trigger findings:
   - `//` line comments
   - `/* ... */` block comments — Scala block comments **do** nest,
     and the masker honours that nesting
   - `"..."` strings with `\` escapes
   - `"""..."""` triple-quoted raw strings
   - `'x'` and `'\n'` character literals
3. Scan for the patterns above. The three "method-call" patterns
   require a Toolbox-context token nearby (same line or the previous
   4 lines).
4. Emit one finding per match: `path:line: scala-toolbox-eval[name]: <code>`.

## Run

```bash
python3 detect.py path/to/file.scala
python3 detect.py path/to/dir/
```

Exit code = number of findings (capped at 255).

## Verify (bundled examples)

```bash
$ python3 detect.py examples/bad examples/good
examples/bad/06_repl.scala:1: scala-toolbox-eval[import-ToolBox]: import scala.tools.reflect.ToolBox
examples/bad/06_repl.scala:5: scala-toolbox-eval[mkToolBox]: scala.reflect.runtime.currentMirror.mkToolBox()
examples/bad/06_repl.scala:8: scala-toolbox-eval[toolbox-compile]: val out = toolbox.compile(toolbox.parse(input))()
examples/bad/06_repl.scala:8: scala-toolbox-eval[toolbox-parse]: val out = toolbox.compile(toolbox.parse(input))()
examples/bad/05_split_parse_eval.scala:1: scala-toolbox-eval[import-ToolBox]: import scala.tools.reflect.ToolBox
examples/bad/05_split_parse_eval.scala:5: scala-toolbox-eval[mkToolBox]: val tb = u.runtimeMirror(getClass.getClassLoader).mkToolBox()
examples/bad/05_split_parse_eval.scala:8: scala-toolbox-eval[toolbox-parse]: val tree = tb.parse(code)
examples/bad/05_split_parse_eval.scala:9: scala-toolbox-eval[toolbox-eval]: val result = tb.eval(tree)
examples/bad/03_braced_import.scala:1: scala-toolbox-eval[import-ToolBox]: import scala.tools.reflect.{ToolBox, ToolBoxError}
examples/bad/03_braced_import.scala:5: scala-toolbox-eval[mkToolBox]: val tb = cm.mkToolBox()
examples/bad/03_braced_import.scala:7: scala-toolbox-eval[toolbox-parse]: val tree = tb.parse(s"($rule): Boolean")
examples/bad/03_braced_import.scala:8: scala-toolbox-eval[toolbox-eval]: tb.eval(tree).asInstanceOf[Boolean]
examples/bad/01_eval_parse.scala:1: scala-toolbox-eval[import-ToolBox]: import scala.tools.reflect.ToolBox
examples/bad/01_eval_parse.scala:5: scala-toolbox-eval[mkToolBox]: val tb = scala.reflect.runtime.currentMirror.mkToolBox()
examples/bad/01_eval_parse.scala:6: scala-toolbox-eval[toolbox-eval]: def run(src: String): Any = tb.eval(tb.parse(src))
examples/bad/01_eval_parse.scala:6: scala-toolbox-eval[toolbox-parse]: def run(src: String): Any = tb.eval(tb.parse(src))
examples/bad/02_compile.scala:1: scala-toolbox-eval[import-ToolBox]: import scala.tools.reflect.ToolBox
examples/bad/02_compile.scala:5: scala-toolbox-eval[mkToolBox]: private val toolbox = mirror.mkToolBox()
examples/bad/02_compile.scala:7: scala-toolbox-eval[toolbox-compile]: toolbox.compile(toolbox.parse(code))
examples/bad/02_compile.scala:7: scala-toolbox-eval[toolbox-parse]: toolbox.compile(toolbox.parse(code))
examples/bad/04_runtime_mirror.scala:1: scala-toolbox-eval[import-ToolBox]: import scala.tools.reflect.ToolBox
examples/bad/04_runtime_mirror.scala:6: scala-toolbox-eval[mkToolBox]: val tb = universe.runtimeMirror(getClass.getClassLoader).mkToolBox()
examples/bad/04_runtime_mirror.scala:7: scala-toolbox-eval[toolbox-eval]: tb.eval(tb.parse(src))
examples/bad/04_runtime_mirror.scala:7: scala-toolbox-eval[toolbox-parse]: tb.eval(tb.parse(src))
--- 24 finding(s) ---
```

* `examples/bad/` has 6 files; every one is flagged (24 findings total
  because each file exercises multiple sinks: import + mkToolBox +
  parse/eval/compile).
* `examples/good/` has 4 files — `LocalDate.parse`, `Regex.compile`,
  a doc-only block comment mentioning `tb.eval` in prose, and unrelated
  `Future.successful` / JSON parser — all return 0 findings.

## Limitations

- Aliasing through arbitrary identifiers is not tracked. If you do
  `val z = currentMirror.mkToolBox(); val r = z.eval(z.parse(s))`,
  the `z.eval`/`z.parse` calls would still fire because the
  `currentMirror` token sits within the 4-line window. But
  `class MyEvaluator(z: ToolBox)` followed many lines later by
  `z.eval(...)` with no nearby context token would be missed.
- The 4-line gating window is a heuristic. If you have a 200-line
  class where the only `mkToolBox` is at the top and the `eval`
  is 100 lines below, the `eval` will not be flagged. The `import`
  and `mkToolBox` lines will still be flagged, which is enough to
  alert a reviewer.
- Scala 3 macro-quote / `quoted.staging` (`scala.quoted.staging.run`)
  is a separate sink not covered here. A future template can target
  it specifically.
- `'foo` Scala-2 symbol literals are not matched by the masker; in
  practice this is harmless (symbols don't contain method calls).
