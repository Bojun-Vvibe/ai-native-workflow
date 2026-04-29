-- bad/02_interpret_var.hs — interpret with a dynamic expression.
module Bad02 where
import Language.Haskell.Interpreter

doIt :: String -> Interpreter (IO ())
doIt expr = interpret expr (as :: IO ())
