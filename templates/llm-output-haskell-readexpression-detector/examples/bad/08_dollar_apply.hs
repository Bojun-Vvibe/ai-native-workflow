-- bad/08_dollar_apply.hs — `$` application form: eval $ payload.
module Bad08 where
import Language.Haskell.Interpreter

go :: String -> Interpreter String
go payload = eval $ payload
