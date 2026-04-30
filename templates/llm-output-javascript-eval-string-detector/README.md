# llm-output-javascript-eval-string-detector

Static detector for the JavaScript `eval(<dynamic-string>)` and
`new Function(<dynamic-body>)` anti-patterns — the canonical CWE-95
("Eval Injection") shape.

Why an LLM emits this: `eval` is the obvious answer to "evaluate this
expression the user typed", and `new Function(body)` is the
documented escape hatch when the model "knows" `eval` is bad. Both
allow arbitrary JS execution if any input is attacker-controlled.

## What this flags

* **`eval(...)`** — including `window.eval`, `globalThis.eval`,
  `self.eval`, `global.eval` — when the single argument is anything
  other than a single static string literal. String concatenation,
  template literals with `${...}` interpolation, identifiers, member
  access, and function calls all fire.
* **`new Function(...)`** — when the *last* argument (the function
  body) is anything other than a single static string literal.
  Static parameter names with a static body are NOT flagged.

A bare `eval("1 + 1")` is intentionally NOT flagged — it's still
poor style but cannot inject attacker input. A bare
`new Function("x", "y", "return x + y;")` is similarly ignored.

Suppress with `// llm-allow:js-eval-dynamic` on the same logical
line as the call.

## What is NOT flagged

* `JSON.parse(text)` — the right tool for the job.
* `setTimeout(fn, ms)` / `setInterval(fn, ms)` with a function
  reference (not a string).
* `myObj.Function(input)` — only the global `Function` constructor
  via `new Function(...)` matches.
* Identifiers that happen to contain `eval` (e.g. `myEval(x)`).

## Source masking

JS `//` and `/* */` comments and string literal *interiors* are
masked before scanning, so docstring-style examples and string
constants mentioning `eval(` don't fire. Template literal interiors
are masked too, but `${...}` interpolation boundaries are preserved
so the detector can tell "this template was dynamic". Fenced
` ```js ` / ` ```ts ` / ` ```jsx ` / ` ```tsx ` blocks in Markdown
are extracted and scanned.

## CWE references

* **CWE-95**: Improper Neutralization of Directives in Dynamically
  Evaluated Code ('Eval Injection').
* **CWE-94**: Improper Control of Generation of Code ('Code
  Injection').
* **CWE-1336**: Improper Neutralization of Special Elements Used in
  a Template Engine.

## Usage

```
python3 detect.py <file_or_dir> [...]
```

Scans `.js`, `.mjs`, `.cjs`, `.jsx`, `.ts`, `.tsx`, `.md`,
`.markdown`. Exit code `1` on any findings, `0` otherwise. Python 3
stdlib only — no Node, no acorn, no TypeScript compiler required.

## Worked example

```
$ bash verify.sh
bad findings:  9 (rc=1)
good findings: 0 (rc=0)
PASS
```

The fixtures in `examples/bad/sinks.js` exercise nine unsafe
shapes (bare `eval(id)`, `eval` of concat, `eval` of template with
interpolation, `window.eval`, `globalThis.eval`, `new Function`
with dynamic body, `new Function` with single dynamic arg, `eval`
of member access, `eval` of template with single interpolation),
and the detector flags all nine. The fixtures in
`examples/good/sinks.js` exercise static-literal `eval`, static-
literal `new Function`, zero-arg `new Function`, `JSON.parse`,
`setTimeout` with function reference, suppressed audited call,
comment-only mention, string-literal mention, an unrelated `myEval`
identifier, a template with no interpolation, and a custom object
with a `Function` property — zero of them fire.

## Limitations

* Heuristic only — not an AST analyzer. A `new Function` invoked
  via `Reflect.construct(Function, [body])` is missed.
* `eval?.(x)` (optional-call form) is not yet matched.
* `indirect eval` via `(0, eval)(x)` and `Function('return this')()`
  patterns escape this detector — those are common sandbox-escape
  shapes, not LLM-emitted patterns.
* No interprocedural taint tracking — a static literal that was
  itself built from concatenation upstream will not be flagged.
