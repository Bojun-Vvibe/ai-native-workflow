# llm-output-coldfusion-cfexecute-detector

Detect shell-out and dynamic-eval sinks in ColdFusion / CFML source.

## Why

CFML (Adobe ColdFusion, Lucee) ships several primitives that take a
runtime string and either spawn a process or compile-and-run code:

* `<cfexecute name="..." arguments="...">`  -- direct shell exec
* `cfexecute(name="...", arguments="...")`  -- script-syntax form
* `evaluate("...")`                          -- compile + run a CFML
  expression string
* `precisionEvaluate("...")`                 -- same threat model
* `iif(cond, "de('a')", "de('b')")`          -- the second/third
  arguments are CFML expression strings
* `<cfmodule template="#dynamic#">`          -- arbitrary template
  load when the path is built from input

LLM-generated admin pages and "let the user run a quick formula"
recipes routinely concatenate request scope (`form.x`, `url.x`,
`cgi.x`) into one of these strings, giving an attacker remote code
execution against the JVM the CFML engine runs on.

## What this flags

After blanking `<!--- ... --->` CFML comments, `// ...EOL` and
`/* ... */` script comments, and the contents of `"..."` and
`'...'` string literals, the scanner looks for:

| Pattern                                 | Kind                            |
| --------------------------------------- | ------------------------------- |
| `<cfexecute ` ... `name="..."`          | `cfml-cfexecute-tag`            |
| `cfexecute(` (script form)              | `cfml-cfexecute-script`         |
| `evaluate(` (function call)             | `cfml-evaluate`                 |
| `precisionEvaluate(`                    | `cfml-precision-evaluate`       |
| `iif(` (function call)                  | `cfml-iif`                      |
| `<cfmodule ` ... `template="..."`       | `cfml-cfmodule`                 |

A finding is upgraded to `-dynamic` when the surviving span (after
string blanking) still contains either `#...#` interpolation or a
`scope.var` reference (`form.`, `url.`, `cgi.`, `arguments.`,
`session.`, `client.`, `cookie.`, `request.`).

## Suppression

Append `<!--- cfml-exec-ok --->` (or `// cfml-exec-ok` in script
syntax) on the same line.

## Fixtures

* `examples/bad/` -- 6 files: tag-form `cfexecute`, script-form
  `cfexecute`, `evaluate(form.x)`, `precisionEvaluate` with `#x#`,
  `iif` with dynamic branch, `cfmodule` with dynamic template.
* `examples/good/` -- 4 files: parameterized `cfquery`, plain
  `cfoutput` with no sinks, suppressed `evaluate("1 + 1")` line,
  and mention only inside a CFML block comment.

## Usage

    python3 detector.py <file_or_dir> [...]

Recurses into directories looking for `*.cfm`, `*.cfml`, `*.cfc`.
Exit 1 if findings, 0 otherwise. python3 stdlib only.

## Exit codes

* `0` -- no findings
* `1` -- one or more findings
* `2` -- usage error
