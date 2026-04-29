# llm-output-haskell-readexpression-detector

Pure-stdlib python3 single-pass scanner that flags **dangerous,
dynamic** invocations of the `hint` package's runtime-evaluation
sinks — `eval`, `interpret`, and `runStmt` — in Haskell source
files (`*.hs`, `*.lhs`).

The `hint` package (`Language.Haskell.Interpreter`) embeds the GHC
API and lets a Haskell program parse and execute a `String` as
Haskell code at runtime. The three primary sinks are:

* `eval :: String -> Interpreter String` — evaluate an expression.
* `interpret :: String -> a -> Interpreter a` — evaluate and coerce
  to a target type.
* `runStmt :: String -> Interpreter ()` — execute a statement.

When the `String` argument is built from user input, an attacker
gains arbitrary Haskell execution: `IO` actions, FFI, file writes,
process spawning. LLMs reach for `interpret userInput (as :: IO ())`
when asked for a "small DSL" or "let users write formulas" — exactly
the shape this scanner exists to catch. A literal `eval "1 + 1"`
(only string-literal characters between the quotes) is **not**
flagged. The scanner only inspects files that contain an
`import Language.Haskell.Interpreter` line, so locally-defined
functions that happen to be named `eval` / `interpret` in unrelated
modules are not false-positived. Suppress an audited line with a
trailing `-- hint-ok` comment.
