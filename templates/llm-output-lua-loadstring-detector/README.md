# llm-output-lua-loadstring-detector

Pure-stdlib python3 single-pass scanner that flags Lua dynamic-code
execution sinks (`loadstring`, string-form `load`, `:dostring`) in
Lua source files.

## What it detects

In Lua, `loadstring(s)` (5.1) and `load(s)` (5.2+, when given a
string) compile arbitrary source text into a callable chunk; calling
that chunk executes the source in the current Lua state. Any value
that flows from input or from string concatenation into these
functions is a code-injection sink with the same blast radius as
`system($USER_INPUT)`.

LLM-emitted Lua reaches for `loadstring` / `load` to "evaluate an
expression the user typed" or "build a function from a template
string" — almost always wrong. Safe alternatives:

* a small dispatch table over allowed operations,
* a sandboxed `_ENV` (5.2+) / `setfenv` (5.1) plus a whitelisted
  function table,
* pre-compiled functions chosen at runtime by name.

The detector flags the *call itself* — it does not try to prove that
the argument is a constant literal, because even constant-string
`load` is a smell worth a human glance. Suppress an audited line with
a trailing `-- loadstring-ok` comment.

## What gets scanned

* Files with extension `.lua`.
* Files whose first line is a shebang containing `lua`.
* Directories are recursed.

## What gets flagged

* `loadstring(...)` — Lua 5.1 / LuaJIT.
* `load(...)` — Lua 5.2+ string form. (The reader-function form
  `load(function() return chunk end)` is also flagged because the
  detector cannot prove the argument type without parsing; suppress
  with `-- loadstring-ok` after audit.)
* `obj:dostring(...)` — LuaSocket / LuaJIT-style method form.

Out of scope (deliberately): `dofile` and `loadfile` read from a
path rather than an in-memory dynamic string; a separate detector
can target those.

## False-positive notes

* `loadstring` / `load` / `:dostring` inside a `--` comment, a
  short-string literal (`'...'` / `"..."`), or a single-line long
  bracket (`[[...]]`) is masked out before scanning.
* `-- loadstring-ok` on a line suppresses that line entirely.
* Multi-line long brackets that span lines are not tracked across
  lines; in practice LLM-emitted Lua almost never triggers this.

## Usage

```
python3 detect.py <file_or_dir> [<file_or_dir> ...]
```

Exits 1 if any findings, 0 otherwise. Output format:

```
<path>:<line>:<col>: lua-loadstring — <stripped source line>
# <N> finding(s)
```

## Smoke test (verified)

```
$ python3 detect.py examples/bad.lua
examples/bad.lua:7:12: lua-loadstring — local f1 = loadstring("return " .. user_expr)
examples/bad.lua:11:12: lua-loadstring — local f2 = load("return " .. user_expr)
examples/bad.lua:15:14: lua-loadstring — print(assert(loadstring(user_expr))())
examples/bad.lua:19:15: lua-loadstring — local maker = load(tmpl)
examples/bad.lua:24:8: lua-loadstring — sandbox:dostring("return os.time()")
examples/bad.lua:31:11: lua-loadstring — local g = load(user_expr)
# 6 finding(s)

$ python3 detect.py examples/good.lua
# 0 finding(s)
```

bad: **6** findings, good: **0** findings.
