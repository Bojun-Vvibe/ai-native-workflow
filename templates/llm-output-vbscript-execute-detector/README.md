# llm-output-vbscript-execute-detector

Single-pass detector for **VBScript `Execute`, `ExecuteGlobal`, and
`Eval`** runtime code-evaluation sinks.

## Why this exists

Classic VBScript (and the VBA dialect that piggy-backs on it inside
Office documents and Windows Script Host) ships three built-in
statements that take a string and run it as VBScript:

```vbs
Execute       expr_string         ' run as a sequence of statements
ExecuteGlobal expr_string         ' run in the global scope
result = Eval(expr_string)        ' evaluate as a single expression
```

Whenever the string is anything other than a manifest, audited
literal, the program is loading code chosen at runtime from data
that may be attacker-controllable: an `InputBox`, a registry value,
the body of an HTTP response read through `MSXML2.ServerXMLHTTP`, a
field in an `ADODB.Recordset`, or a parameter passed to a
`WScript.Shell` script.

LLM-emitted VBScript reaches for `Execute` whenever the model wants
"a tiny config DSL", "let the user supply a one-liner formula", or
"run a snippet from a file" without knowing the safer patterns
(parsing a fixed grammar, dispatching on a small enum of allowed
operations, or moving the dynamic surface to a sandboxed JScript
host with `Microsoft.JScript`'s `eval` disabled).

## What it flags

| Construct                       | Why                                       |
| ------------------------------- | ----------------------------------------- |
| `Execute s`                     | Primary statement sink                    |
| `Execute(s)`                    | Same, in call-syntax form                 |
| `ExecuteGlobal s`               | Global-scope variant                      |
| `Eval(expr)` / `Eval expr`      | Expression-evaluation variant             |

The match is anchored on the keyword followed by either whitespace
(statement form) or `(` (call form), so identifiers that merely
contain `Execute` or `Eval` (`ExecuteWorkbook`, `EvalScore`,
`MyExecutor`) are not flagged.

## What it ignores

- Mentions inside `'` line comments and `Rem` line comments.
- Mentions inside `"..."` string literals (with the VBScript
  doubled-quote `""` escape rule).
- Identifiers that happen to share a prefix (see above).
- Lines marked with the suppression comment `' execute-ok`.

## Usage

```sh
python3 detect.py <file_or_dir> [<file_or_dir> ...]
```

Exit code `1` on any finding, `0` otherwise. Python 3 stdlib only,
no third-party dependencies. Recurses into directories looking for
`*.vbs`, `*.vbe`, `*.wsf`, and `*.bas`.

## Verified output

```
$ python3 detect.py examples/
examples/bad/01_execute_input.vbs:3:1: vbscript-execute — Execute userCode
examples/bad/02_execute_global.vbs:4:1: vbscript-execute-global — ExecuteGlobal pluginText
examples/bad/03_eval_call.vbs:3:10: vbscript-eval — result = Eval(formula)
examples/bad/04_execute_paren.vbs:2:1: vbscript-execute — Execute(snippet)
examples/bad/05_loop_execute.vbs:5:5: vbscript-execute — Execute lines(i)
examples/bad/06_eval_statement.vbs:2:1: vbscript-eval — Eval expr
# 6 finding(s)
```

The `examples/good/` files correctly produce zero findings, including
the doc strings that mention `Execute` inside literals, lookalike
identifiers like `ExecuteWorkbook`, the `Rem`-commented mention, and
the `' execute-ok` suppressed line.

## Layout

```
detect.py                    # the scanner
examples/bad/*.vbs           # six intentional violations
examples/good/*.vbs          # four files with zero violations
```
