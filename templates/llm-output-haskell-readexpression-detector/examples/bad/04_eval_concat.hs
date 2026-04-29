-- bad/04_eval_concat.hs — eval of a concatenation that mixes literal
-- prefix with attacker data.
module Bad04 where
import Language.Haskell.Interpreter

wrap :: String -> Interpreter String
wrap user = eval ("show (" ++ user ++ ")")
