-- bad/07_interpret_call.hs — first arg is a function call, not a
-- string literal.
module Bad07 where
import Language.Haskell.Interpreter

build :: String -> String
build = id

run :: String -> Interpreter Int
run u = interpret (build u) (as :: Int)
