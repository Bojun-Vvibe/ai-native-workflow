# llm-output-lua-pcall-result-discarded-detector

Flags `pcall(...)` and `xpcall(...)` invocations in Lua sources whose
return value is thrown away by being used as a bare statement.

## The smell

```lua
local function refresh_feed(url)
    pcall(http.request, url)   -- <-- result not bound
    return "ok"
end
```

`pcall` exists for *exactly one reason*: convert a raised error into a
`(false, err)` tuple so the caller can decide what to do. Calling it
as a statement collapses that back into a silent swallow — strictly
worse than calling `http.request(url)` directly, because at least
without `pcall` the error would crash and be visible.

## Why LLMs produce it

When asked to "make this safer" or "add error handling" in Lua, the
model reaches for `pcall` because that is the canonical answer to
"how do I not crash on errors in Lua". But the second half of the
contract — *inspect the boolean it returns* — is missing from a lot
of beginner-tutorial training data. The result is "wrap it in pcall
and move on", which neutralises the very crash the wrapper exists to
report.

## How the detector works

Single-pass scanner over `.lua` files:

1. **Mask comments and string literals.** `--` line comments,
   `--[==[ ]==]` long-bracket block comments (any equals-sign count),
   single- and double-quoted strings, and `[==[ ]==]` long-bracket
   strings are all blanked out so that a `pcall(foo)` mentioned in
   prose or test-fixture text does not trigger.
2. **Split each line on top-level `;`** (Lua's optional statement
   separator) so that `pcall(a) ; pcall(b)` is examined as two
   independent statements rather than one consumed expression.
3. **For each `pcall(` / `xpcall(`** check the immediate left context
   inside its statement. If the preceding tokens contain any of
   `=`, `local`, `return`, `if`, `elseif`, `while`, `until`, `and`,
   `or`, `not`, `assert(`, a `,` (call-argument), or an open `(`
   (call-argument position), the result is being consumed and we
   skip. Otherwise, flag.
4. **Right context** is also checked: `pcall(f)()` chains the result,
   so anything non-empty after the matching `)` is treated as
   consumption.

Stdlib only.

## False-positive caveats

- A `pcall` whose result is captured by an *outer* `pcall` on a
  different line (rare in practice) will be flagged — the detector
  does not span statements across lines.
- A custom `pcall` shadow (e.g., `local pcall = require("mymod").pcall`)
  with semantics that intentionally drop the boolean is treated the
  same as the stdlib — this is a feature, since such a shadow is
  itself a smell.
- `pcall(f)` written as `;pcall(f);` to silence a linter is still
  flagged. That is the correct behaviour.

## Usage

```
python3 detector.py path/to/lua/project
```

Exit code `0` if no hits, `1` if any.

## Worked example

Run against the bundled bad fixtures:

```
$ python3 detector.py templates/llm-output-lua-pcall-result-discarded-detector/bad
templates/llm-output-lua-pcall-result-discarded-detector/bad/loop_swallow.lua:7: pcall result discarded at col 9: the (ok, err) tuple is thrown away — error is silently swallowed; bind it: `local ok, err = pcall(...)` and check `ok`
templates/llm-output-lua-pcall-result-discarded-detector/bad/swallow_http.lua:6: pcall result discarded at col 5: the (ok, err) tuple is thrown away — error is silently swallowed; bind it: `local ok, err = pcall(...)` and check `ok`
templates/llm-output-lua-pcall-result-discarded-detector/bad/swallow_decode.lua:6: xpcall result discarded at col 5: the (ok, err) tuple is thrown away — error is silently swallowed; bind it: `local ok, err = xpcall(...)` and check `ok`
templates/llm-output-lua-pcall-result-discarded-detector/bad/swallow_decode.lua:11: pcall result discarded at col 9: the (ok, err) tuple is thrown away — error is silently swallowed; bind it: `local ok, err = pcall(...)` and check `ok`
templates/llm-output-lua-pcall-result-discarded-detector/bad/swallow_decode.lua:11: pcall result discarded at col 34: the (ok, err) tuple is thrown away — error is silently swallowed; bind it: `local ok, err = pcall(...)` and check `ok`
-- 5 hit(s)
```

Counts: `bad/` = 5 hits across 3 files (with 1 file containing two
statements separated by `;`), `good/` = 0 hits across 3 files
(including a fixture full of `pcall(...)` mentions inside long-bracket
comments and strings, exercising the masker).
