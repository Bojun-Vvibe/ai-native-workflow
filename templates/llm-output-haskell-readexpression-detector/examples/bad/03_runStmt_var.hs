-- bad/03_runStmt_var.hs — runStmt of an attacker-controlled stmt.
module Bad03 where
import Language.Haskell.Interpreter

go :: String -> Interpreter ()
go s = runStmt s
