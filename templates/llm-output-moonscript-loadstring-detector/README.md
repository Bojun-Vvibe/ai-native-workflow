# llm-output-moonscript-loadstring-detector

Pure-stdlib python3 single-pass scanner that flags MoonScript dynamic-code
execution sinks (`loadstring`, string-form `load`, `:dostring`) in
MoonScript source files.

## What it detects

MoonScript compiles to Lua, so it inherits Lua's dynamic-code surface:

* `loadstring s` — Lua 5.1 / LuaJIT, compiles a string into a chunk.
* `load s` — Lua 5.2+ string-form, same blast radius.
* `obj\dostring s` — MoonScript-style method call (compiles to
  `obj:dostring(s)` in Lua), shipped by some Lua bindings.

Any value that flows from input or string concatenation into these
functions is a code-injection sink equivalent to
`os.execute($USER_INPUT)`.

LLM-emitted MoonScript reaches for `loadstring` / `load` to "evaluate
an expression the user typed" or "build a function from a template
string" — almost always wrong. Safe alternatives:

* a small dispatch table over allowed operations,
* a sandboxed `_ENV` (5.2+) / `setfenv` (5.1) plus a whitelisted
  function table,
* pre-compiled functions chosen at runtime by name.

The detector flags the *call itself* — it does not try to prove the
argument is a constant literal, because even constant-string `load`
is a smell worth a human glance.

## What gets scanned

* Files with extension `.moon`.
* Files whose first line is a shebang containing `moon`.
* Directories are recursed.

## What gets flagged

* `loadstring …` / `loadstring(…)` at call position.
* `load …` / `load(…)` at call position.
* `obj\dostring …` — MoonScript method-call syntax.

Out of scope (deliberately): `dofile` / `loadfile` (path-based);
`require` (module path, not arbitrary code).

## False-positive notes

* Tokens inside a `--` comment or a short-string literal
  (`'...'` / `"..."`) are masked out before scanning.
* `-- loadstring-ok` on a line suppresses that line entirely.
* MoonScript allows call without parens; both `load s` and `load(s)`
  are flagged.

## Usage

```
python3 detect.py <file_or_dir> [<file_or_dir> ...]
```

Exits 1 if any findings, 0 otherwise.

## Verified worked example

Run `./verify.sh` from this directory. It scans `examples/bad/` and
asserts ≥ 6 findings, then scans `examples/good/` and asserts 0
findings. Exits 0 on success.
