# llm-output-smalltalk-compiler-evaluate-detector

Pure-stdlib python3 single-pass scanner that flags runtime
string-evaluation anti-idioms in Smalltalk source files (Pharo,
Squeak, GNU Smalltalk, Cuis, VisualWorks, Dolphin).

## What it detects

Every mainstream Smalltalk dialect ships a first-class
metacircular evaluator. The canonical spellings for "compile and
run an arbitrary string right now" are:

```smalltalk
Compiler evaluate: aString.
Compiler evaluate: aString for: anObject.
OpalCompiler new source: aString; evaluate.
Smalltalk compiler evaluate: aString.
Smalltalk compileString: aString.
aString asExpression.
'1 + 2' evaluate.
RBParser parseExpression: aString.
```

Any of these, fed user-controlled or otherwise untrusted text, is
arbitrary-code execution inside the image — full filesystem,
sockets, reflection, image surgery.

The detector flags:

| Kind                       | Pattern                                                |
| -------------------------- | ------------------------------------------------------ |
| `compiler-evaluate`        | `Compiler evaluate:` (with optional `for:`/`logged:`)  |
| `opal-compiler`            | `OpalCompiler ... evaluate` chain                      |
| `smalltalk-compiler`       | `Smalltalk compiler evaluate:`                         |
| `smalltalk-compilestring`  | `Smalltalk compileString:`                             |
| `as-expression`            | `<receiver> asExpression`                              |
| `rbparser-expr`            | `RBParser parseExpression:`                            |
| `parser-new-parse`         | `Parser new parse:`                                    |
| `smaccparser-parse`        | `SmaCCParser parse:`                                   |
| `classbuilder-compile`     | `ClassBuilder ... compile:`                            |
| `string-evaluate`          | line has both a `'...'` literal and a bare `evaluate`  |

## What gets scanned

* Files with extension `.st`, `.cs` (Cincom file-out), `.changes`.
* Directories are recursed.
* `.cs` overlaps with C#; if that's a problem in your repo, pass
  individual files instead of a directory.

## False-positive notes

* Bare references to the `Compiler` class symbol (with no
  `evaluate` message) are **not** flagged — that's reflection,
  not eval.
* Smalltalk `"..."` comments (which can span lines) and `'...'`
  string literals (with the `''` doubled-apostrophe escape) are
  masked out before scanning.
* The `string-evaluate` heuristic suppresses itself if a more
  specific kind already matched on the same line.

## Suppression

Trailing `"eval-string-ok"` comment on the same line suppresses
that finding. The literal token `eval-string-ok` anywhere on the
line will suppress — use sparingly and never on user-tainted
input.

## Usage

```
python3 detect.py <file_or_dir> [<file_or_dir> ...]
```

Exits 1 if any findings, 0 otherwise. Output format:

```
<path>:<line>:<col>: <kind> — <stripped source line>
# <N> finding(s)
```

## Smoke test (verified locally)

```
$ python3 detect.py examples/bad.st
examples/bad.st:7:11:  compiler-evaluate     — result := Compiler evaluate: src.
examples/bad.st:10:11: compiler-evaluate     — result := Compiler evaluate: src for: obj.
examples/bad.st:13:11: opal-compiler         — result := OpalCompiler new source: src; evaluate.
examples/bad.st:16:11: smalltalk-compiler    — result := Smalltalk compiler evaluate: src.
examples/bad.st:19:1:  smalltalk-compilestring — Smalltalk compileString: src.
examples/bad.st:22:15: as-expression         — result := src asExpression.
examples/bad.st:25:11: rbparser-expr         — result := RBParser parseExpression: src.
examples/bad.st:28:11: parser-new-parse      — result := Parser new parse: src class: UndefinedObject.
examples/bad.st:31:11: smaccparser-parse     — result := SmaCCParser parse: src.
examples/bad.st:34:11: classbuilder-compile  — result := ClassBuilder new compile: 'foo ^ 1'.
examples/bad.st:37:19: string-evaluate       — result := '1 + 2' evaluate.
# 11 finding(s)

$ python3 detect.py examples/good.st
# 0 finding(s)
```

bad: **11** findings across all ten detector kinds. good: **0**
findings (covers plain do-loop arithmetic with no eval, the
dangerous identifiers mentioned only inside multi-line `"..."`
Smalltalk comments, the same identifiers mentioned inside
`'...'` string literals using doubled-apostrophe escapes, a bare
reference to the `Compiler` class symbol with no message send,
and one `"eval-string-ok"` suppression on a fixture-only path).
