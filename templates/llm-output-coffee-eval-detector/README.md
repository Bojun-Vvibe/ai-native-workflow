# llm-output-coffee-eval-detector

Pure-stdlib python3 single-pass scanner that flags CoffeeScript
dynamic-code execution sinks (`eval`, `Function(string)`, `vm.runInThisContext`)
in CoffeeScript source files.

## What it detects

CoffeeScript compiles to JavaScript, so it inherits the JS dynamic-
code surface:

* `eval s` — direct or indirect `eval` runs `s` as JS in the current
  scope (direct) or global scope (indirect).
* `new Function s` / `Function s` — compiles a string into a
  callable; same blast radius as `eval` minus local-scope capture.
* `vm.runInThisContext s` — Node's `vm` module, runs string in the
  current context.
* `setTimeout s, n` / `setInterval s, n` — when the first argument
  is a string (not a function), the runtime `eval`s it.

Any value flowing from input or string concatenation into these
functions is a code-injection sink equivalent to
`exec($USER_INPUT)`.

LLM-emitted CoffeeScript reaches for `eval` or `Function` to
"evaluate an expression the user typed" or "build a function from a
template string" — almost always wrong. Safe alternatives:

* a small dispatch object over allowed operations,
* a sandboxed `vm.runInNewContext` with a minimal `contextObject`,
* pre-compiled functions chosen at runtime by name.

The detector flags the *call itself* — it does not try to prove the
argument is a constant literal, because even constant-string `eval`
is a smell worth a human glance.

## What gets scanned

* Files with extension `.coffee`.
* Files whose first line is a shebang containing `coffee`.
* Directories are recursed.

## What gets flagged

* `eval(…)` / `eval …` at call position.
* `new Function …` / `Function(…)` at call position.
* `vm.runInThisContext(…)` and `vm.runInThisContext …`.
* `setTimeout "…", n` / `setInterval "…", n` (string first arg).

Out of scope (deliberately): `require` (module path, not arbitrary
code); `vm.runInNewContext` (typically used *with* a sandbox, but a
separate detector can target unsandboxed forms).

## False-positive notes

* Tokens inside `#` line comments, `###...###` block comments, or
  string literals (`'...'`, `"..."`, triple-quoted) are masked out.
* `# eval-ok` on a line suppresses that line entirely.
* CoffeeScript allows call without parens; both `eval s` and
  `eval(s)` are flagged.

## Usage

```
python3 detect.py <file_or_dir> [<file_or_dir> ...]
```

Exits 1 if any findings, 0 otherwise.

## Verified worked example

Run `./verify.sh` from this directory. It scans `examples/bad/` and
asserts ≥ 6 findings, then scans `examples/good/` and asserts 0
findings. Exits 0 on success.
