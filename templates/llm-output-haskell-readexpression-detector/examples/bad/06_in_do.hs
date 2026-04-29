-- bad/06_in_do.hs — sink call inside a do-block, after a `;` /
-- semicolon-style separator.
module Bad06 where
import Language.Haskell.Interpreter

action :: String -> Interpreter ()
action s = do { runStmt s; return () }
