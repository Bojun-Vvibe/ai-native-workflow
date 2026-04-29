-- bad/05_qualified.hs — qualified import, full path qualifier.
module Bad05 where
import qualified Language.Haskell.Interpreter as Hint

go :: String -> Hint.Interpreter String
go x = Hint.eval x
