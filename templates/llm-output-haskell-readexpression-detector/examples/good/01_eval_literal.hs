-- good/01_eval_literal.hs — fully literal string argument. No
-- attacker-controlled component. Detector skips.
module Good01 where
import Language.Haskell.Interpreter

addOne :: Interpreter String
addOne = eval "1 + 1"

showFortyTwo :: Interpreter String
showFortyTwo = eval "show 42"
