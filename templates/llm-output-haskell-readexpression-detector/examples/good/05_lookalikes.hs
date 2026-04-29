-- good/05_lookalikes.hs — record field, type signature, identifier
-- merely *named* `eval` / `interpret`. None of these are calls into
-- the hint runtime-eval sink. Crucially, this file does NOT import
-- Language.Haskell.Interpreter, so the detector skips it entirely.
module Good05 where

data Strategy = Strategy { eval :: Int -> Int, name :: String }

myStrategy :: Strategy
myStrategy = Strategy { eval = (+ 1), name = "inc" }

-- Function declaration (not a call):
interpret :: Int -> String
interpret n = show n

-- Use the locally-defined `interpret` with a literal:
demo :: String
demo = interpret 42
