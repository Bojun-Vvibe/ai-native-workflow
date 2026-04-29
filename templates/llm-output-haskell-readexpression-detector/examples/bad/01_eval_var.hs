-- bad/01_eval_var.hs — eval of a String variable.
module Bad01 where
import Language.Haskell.Interpreter

run :: String -> Interpreter String
run code = eval code
