# llm-output-groovy-evaluate-string-detector

Pure-stdlib python3 single-pass scanner that flags Groovy dynamic
source-evaluation calls — `Eval.me/x/xy/xyz`, `GroovyShell.evaluate`,
`GroovyShell.run`, and `GroovyClassLoader.parseClass` — in `.groovy`,
`.gvy`, `.gy`, and `.gradle` files.

## What it detects

In Groovy, several APIs take a String of source code and execute it at
runtime. The dangerous family:

* `Eval.me(STRING)` and the binding-aware `Eval.x` / `Eval.xy` /
  `Eval.xyz` variants.
* `new GroovyShell().evaluate(STRING)` and `.run(STRING, ...)`.
* `new GroovyClassLoader().parseClass(STRING)`.

Used on attacker- or developer-templated text these are code-injection
sinks with the same blast radius as `Runtime.exec(USER_INPUT)`. LLM-
emitted Groovy frequently reaches for `Eval.me(scriptString)` to "just
run this snippet" — that is almost always wrong; the safe forms are an
explicit dispatch table or a sandboxed `GroovyShell` configured with a
`SecureASTCustomizer`.

The detector flags the call site itself, regardless of whether the
argument is a literal, a variable, or a triple-quoted heredoc — `Eval.me`
and friends are themselves the smell. Suppress an audited line with a
trailing `// groovy-eval-ok` comment.

## What gets scanned

* Files with extension `.groovy`, `.gvy`, `.gy`, `.gradle`.
* Files whose first line is a shebang containing `groovy`.
* Directories are recursed.

## False-positive notes

* `.evaluate(` is a generic name; the detector only flags it when the
  same line either mentions `GroovyShell` or has a receiver whose
  identifier contains `shell` (case-insensitive). A plain
  `scorer.evaluate(n)` on a domain object is **not** flagged.
* `Eval.me`, `parseClass`, and `GroovyShell(...).run` are flagged
  unconditionally at command position — these names are not used by
  user code for anything benign.
* String literals (`'...'`, `"..."`, triple-quoted) and comments
  (`// ...`, `/* ... */`) are masked before scanning, so an `Eval.me`
  token inside documentation or a warning string is never flagged.
* Multi-line block comments / multi-line triple-quoted strings are
  best-effort (the scrubber is single-pass per line). The worst case
  is a missed flag, not a wrong-column false positive.
* `// groovy-eval-ok` on a line suppresses that line entirely.

## Usage

```
python3 detect.py <file_or_dir> [<file_or_dir> ...]
```

Exits 1 if any findings, 0 otherwise. Output format:

```
<path>:<line>:<col>: <kind> — <stripped source line>
# <N> finding(s)
```

`<kind>` is one of `groovy-eval-me`, `groovy-shell-evaluate`,
`groovy-shell-run`, `groovy-parseclass`.

## Smoke test (verified)

```
$ python3 detect.py examples/bad.groovy
examples/bad.groovy:6:10: groovy-eval-me — def r1 = Eval.me(script)
examples/bad.groovy:9:10: groovy-eval-me — def r2 = Eval.x(42, "x.toString().reverse()")
examples/bad.groovy:13:15: groovy-shell-evaluate — def r3 = shell.evaluate(script)
examples/bad.groovy:16:27: groovy-shell-evaluate — def r4 = new GroovyShell().evaluate("System.getProperty('user.dir')")
examples/bad.groovy:19:5: groovy-shell-run — new GroovyShell().run("println 'pwn'", "inline.groovy", [] as String[])
examples/bad.groovy:23:17: groovy-parseclass — def cls = loader.parseClass("class C { def go() { 'hi' } }")
examples/bad.groovy:26:10: groovy-eval-me — def r7 = Eval.xy("a", "b", "x + y")
examples/bad.groovy:30:10: groovy-eval-me — def r8 = Eval.me(src)
# 8 finding(s)

$ python3 detect.py examples/good.groovy
# 0 finding(s)
```

bad: **8** findings, good: **0** findings.
